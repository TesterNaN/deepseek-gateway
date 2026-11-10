"""离线计费回归：python -m unittest test_billing -v（不调用付费上游）。"""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI, HTTPException

from app import billing, database
from app.api.admin import router as admin_router
from app.api.proxy import router as proxy_router
from app.dependencies import AuthInfo, authenticate_virtual_key, require_admin


def bj(value):
    return datetime.fromisoformat(value).replace(tzinfo=billing.BEIJING)


class PeriodTests(unittest.TestCase):
    def test_boundaries(self):
        for time, expected in [('08:59:59', 'off_peak'), ('09:00:00', 'peak'),
                               ('11:59:59', 'peak'), ('12:00:00', 'off_peak'),
                               ('13:59:59', 'off_peak'), ('14:00:00', 'peak'),
                               ('17:59:59', 'peak'), ('18:00:00', 'off_peak')]:
            with self.subTest(time=time):
                self.assertEqual(billing.get_pricing_period(bj('2026-11-10T' + time)), expected)

    def test_holidays_weekends_and_makeup_workday(self):
        for day in ['2026-10-01', '2026-11-07', '2026-11-08', '2026-10-10']:
            with self.subTest(day=day):
                self.assertEqual(billing.get_pricing_period(bj(day + 'T10:00')), 'off_peak')

    def test_timezone_independence(self):
        self.assertEqual(billing.get_pricing_period(datetime(2026, 11, 10, 1, tzinfo=timezone.utc)), 'peak')
        with self.assertRaises(ValueError):
            billing.get_pricing_period(datetime(2026, 11, 10, 10))

    def test_calendar_out_of_range(self):
        with self.assertRaises(HTTPException) as caught:
            billing.get_pricing_period(bj('2100-01-04T10:00'))
        self.assertEqual(caught.exception.status_code, 503)


class BillingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(database, 'DATABASE', str(Path(self.temp.name) / 'keys.db'))
        self.db_patch.start()
        await database.init_db()
        await database.set_upstream_key('fake-upstream')
        async with database.get_db() as conn:
            await conn.execute("INSERT INTO keys (virtual_key, tenant, balance) VALUES ('sk-test', 'test', 100)")
        self.app = FastAPI()
        self.app.include_router(admin_router)
        self.app.include_router(proxy_router)
        self.app.dependency_overrides[require_admin] = lambda: None
        self.app.dependency_overrides[authenticate_virtual_key] = lambda: AuthInfo('sk-test', 100, False, 0)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://test')

    async def asyncTearDown(self):
        await self.client.aclose()
        self.db_patch.stop()
        self.temp.cleanup()

    async def test_default_prices_and_aliases(self):
        prices = await billing.get_model_pricing()
        self.assertEqual(prices['deepseek-flash'], {'input_hit': .04, 'input_miss': 2, 'output': 8})
        self.assertEqual(prices['deepseek-v4-pro'], {'input_hit': .3, 'input_miss': 9, 'output': 27})
        self.assertEqual(prices['deepseek-v4-flash'], prices['deepseek-flash'])
        self.assertEqual(prices['deepseek-v4-flash-vision-exp'], prices['deepseek-flash'])

    async def test_peak_and_off_peak_cost(self):
        await billing.set_custom_pricing(mode='peak_valley')
        usage = {'prompt_tokens': 2_000_000, 'prompt_cache_hit_tokens': 1_000_000,
                 'completion_tokens': 1_000_000}
        for model, cost in [('deepseek-flash', 10.04), ('deepseek-v4-pro', 36.3), ('deepseek-v4-flash', 10.04)]:
            peak = await billing.get_model_pricing(bj('2026-11-10T10:00'))
            valley = await billing.get_model_pricing(bj('2026-11-10T12:00'))
            self.assertAlmostEqual(billing.calculate_cost(model, usage, peak), cost)
            self.assertAlmostEqual(billing.calculate_cost(model, usage, valley), cost / 2)

    async def test_legacy_config_survives_mode_switch_and_reopen(self):
        custom = {'deepseek-v4-flash': {'input_hit': .02, 'input_miss': 1, 'output': 2}}
        response = await self.client.put('/admin/pricing', json={'models': custom})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['effective']['deepseek-v4-flash'], custom['deepseek-v4-flash'])
        await self.client.put('/admin/pricing', json={'mode': 'peak_valley'})
        settings = await billing.get_pricing_settings(bj('2026-11-10T10:00'))
        self.assertEqual(settings['custom'], custom)
        self.assertEqual(settings['effective']['deepseek-v4-flash']['output'], 8)
        await self.client.put('/admin/pricing', json={'mode': 'fixed'})
        self.assertEqual((await billing.get_model_pricing())['deepseek-v4-flash'], custom['deepseek-v4-flash'])
        response = await self.client.delete('/admin/pricing')
        self.assertTrue(response.json()['is_default'])
        self.assertEqual(response.json()['mode'], 'fixed')

    async def test_invalid_config_does_not_change_prices(self):
        for payload in [{'mode': 'bad'}, {'models': {'x': {'input_hit': -1, 'input_miss': 2, 'output': 8}}},
                        {'models': {'x': {'input_hit': 'NaN', 'input_miss': 2, 'output': 8}}}]:
            response = await self.client.put('/admin/pricing', json=payload)
            self.assertEqual(response.status_code, 422)
        self.assertTrue((await billing.get_pricing_settings())['is_default'])

    async def test_proxy_stream_and_json_lock_prices_before_upstream(self):
        usage = {'prompt_tokens': 1_000_000, 'completion_tokens': 1_000_000}
        for stream in [False, True]:
            with self.subTest(stream=stream):
                await billing.set_custom_pricing({}, 'peak_valley')

                async def upstream(request):
                    # 上游执行期间更改模式及单价；本次扣费仍应使用此前锁定的高峰价。
                    await billing.set_custom_pricing({'deepseek-flash': {'input_hit': 0, 'input_miss': 99, 'output': 99}}, 'fixed')
                    if stream:
                        body = 'data: ' + json.dumps({'usage': usage}) + '\n\ndata: [DONE]\n\n'
                        return httpx.Response(200, text=body, headers={'content-type': 'text/event-stream'})
                    return httpx.Response(200, json={'usage': usage})

                async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as upstream_client:
                    self.app.state.http_client = upstream_client
                    with patch.object(billing, 'get_pricing_period', return_value='peak'):
                        response = await self.client.post('/chat/completions', json={'model': 'deepseek-flash', 'stream': stream})
                    self.assertEqual(response.status_code, 200)
        async with database.get_db() as conn:
            row = await (await conn.execute("SELECT balance, total_consumed FROM keys WHERE virtual_key='sk-test'")).fetchone()
        self.assertAlmostEqual(row['balance'], 80)
        self.assertAlmostEqual(row['total_consumed'], 20)


if __name__ == '__main__':
    unittest.main()
