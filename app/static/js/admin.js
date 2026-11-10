// ---------- 工具 ----------
function showMessage(text, type = 'success') {
    const msg = document.getElementById('message');
    msg.textContent = text;
    msg.className = 'msg ' + type;
    setTimeout(() => { msg.className = 'msg'; }, 5000);
}

function showPricingMsg(text, type = 'success') {
    const msg = document.getElementById('pricingMsg');
    msg.textContent = text;
    msg.className = 'msg ' + type;
    setTimeout(() => { msg.className = 'msg'; }, 5000);
}

// ---------- Key 管理 ----------
function loadKeys() {
    fetch('/admin/keys')
        .then(res => {
            if (res.status === 401 || res.status === 403) {
                window.location.href = '/login';
                return;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return;
            const tbody = document.getElementById('keyTableBody');
            tbody.innerHTML = '';
            data.forEach(row => {
                const enabled = row.concurrency_enabled === 1;
                const limit = row.concurrency_limit || 0;
                const concurrencyDisplay = enabled ? `最多 ${limit} 个` : '关闭';
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><code>${row.virtual_key}</code></td>
                    <td>${row.tenant}</td>
                    <td>¥${parseFloat(row.balance).toFixed(2)}</td>
                    <td>¥${parseFloat(row.total_recharged || 0).toFixed(2)}</td>
                    <td>¥${parseFloat(row.total_consumed || 0).toFixed(2)}</td>
                    <td>${concurrencyDisplay}</td>
                    <td>${row.created_at}</td>
                    <td>
                        <div class="op-cell">
                            <div class="op-row">
                                <input type="number" id="recharge_amt_${row.virtual_key}" value="10.00" step="0.01">
                                <button class="btn-recharge" onclick="recharge('${row.virtual_key}')">充值</button>
                            </div>
                            <div class="op-row">
                                <input type="number" id="set_balance_amt_${row.virtual_key}" value="${parseFloat(row.balance).toFixed(2)}" step="0.01">
                                <button class="btn-set" onclick="setBalance('${row.virtual_key}')">设置余额</button>
                            </div>
                            <div class="op-row">
                                <input type="number" id="concurrency_limit_${row.virtual_key}" value="${limit}" min="0" style="width:50px;">
                                <input type="checkbox" id="concurrency_enabled_${row.virtual_key}" ${enabled ? 'checked' : ''}>
                                <label for="concurrency_enabled_${row.virtual_key}" class="concurrency-label">启用限制</label>
                                <button class="btn-concurrency" onclick="setConcurrency('${row.virtual_key}')">应用</button>
                            </div>
                            <button class="btn-del" onclick="deleteKey('${row.virtual_key}')">删除</button>
                        </div>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(err => showMessage('加载失败: ' + err.message, 'error'));
}

function addKey() {
    const tenant = document.getElementById('new_tenant').value.trim() || 'default';
    const balance = parseFloat(document.getElementById('new_balance').value) || 0;
    fetch('/admin/keys', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tenant, balance})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showMessage('添加失败: ' + (data.error.message || data.error), 'error');
        } else {
            showMessage('添加成功: ' + data.virtual_key);
            loadKeys();
        }
    })
    .catch(err => showMessage('添加失败: ' + err.message, 'error'));
}

function recharge(virtualKey) {
    const amount = parseFloat(document.getElementById('recharge_amt_' + virtualKey).value);
    if (isNaN(amount) || amount <= 0) {
        alert('请输入有效的正数金额');
        return;
    }
    fetch('/admin/keys/' + virtualKey, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'recharge', amount})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showMessage('充值失败: ' + (data.error.message || data.error), 'error');
        } else {
            showMessage('充值成功，增加 ¥' + amount.toFixed(2));
            loadKeys();
        }
    })
    .catch(err => showMessage('充值失败: ' + err.message, 'error'));
}

function setBalance(virtualKey) {
    const amount = parseFloat(document.getElementById('set_balance_amt_' + virtualKey).value);
    if (isNaN(amount) || amount < 0) {
        alert('请输入有效的非负金额');
        return;
    }
    fetch('/admin/keys/' + virtualKey, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'set_balance', amount})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showMessage('设置失败: ' + (data.error.message || data.error), 'error');
        } else {
            showMessage('设置成功，余额变为 ¥' + amount.toFixed(2));
            loadKeys();
        }
    })
    .catch(err => showMessage('设置失败: ' + err.message, 'error'));
}

function setConcurrency(virtualKey) {
    const limit = parseInt(document.getElementById('concurrency_limit_' + virtualKey).value) || 0;
    const enabled = document.getElementById('concurrency_enabled_' + virtualKey).checked;
    fetch('/admin/keys/' + virtualKey, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({action: 'set_concurrency', limit: limit, enabled: enabled})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showMessage('并发设置失败: ' + (data.error.message || data.error), 'error');
        } else {
            showMessage('并发设置成功，限制: ' + (enabled ? `最多 ${limit} 个` : '关闭'));
            loadKeys();
        }
    })
    .catch(err => showMessage('并发设置失败: ' + err.message, 'error'));
}

function deleteKey(virtualKey) {
    if (!confirm('确定要删除 Key ' + virtualKey + ' 吗？')) return;
    fetch('/admin/keys/' + virtualKey, {method: 'DELETE'})
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            showMessage('删除失败: ' + (data.error.message || data.error), 'error');
        } else {
            showMessage('删除成功');
            loadKeys();
        }
    })
    .catch(err => showMessage('删除失败: ' + err.message, 'error'));
}

// ---------- 上游配置 ----------
function loadUpstreamStatus() {
    fetch('/admin/upstream/key')
        .then(res => {
            if (res.status === 401 || res.status === 403) {
                window.location.href = '/login';
                return;
            }
            return res.json();
        })
        .then(data => {
            if (!data) return;
            document.getElementById('upstreamMasked').textContent = data.exists ? data.masked : '未配置';
        })
        .catch(err => console.error(err));
}

function setUpstreamKey() {
    const key = document.getElementById('newUpstreamKey').value.trim();
    if (!key) {
        alert('请输入有效的 Key');
        return;
    }
    fetch('/admin/upstream/key', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({key})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            alert('更新失败: ' + (data.error.message || data.error));
        } else {
            alert('更新成功');
            document.getElementById('newUpstreamKey').value = '';
            loadUpstreamStatus();
        }
    })
    .catch(err => alert('请求失败: ' + err.message));
}

function viewBalance() {
    const resultDiv = document.getElementById('balanceResult');
    resultDiv.innerHTML = '<div class="balance-loading">查询中...</div>';

    fetch('/admin/upstream/balance')
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                resultDiv.innerHTML = `<div class="balance-error">${data.error.message || data.error}</div>`;
                return;
            }

            if (data.balance_infos && data.balance_infos.length > 0) {
                let html = '<div class="balance-list">';
                data.balance_infos.forEach(info => {
                    const isAvailable = data.is_available ? '可用' : '不可用';
                    const availableClass = data.is_available ? 'available' : 'unavailable';

                    html += `
                        <div class="balance-card">
                            <div class="balance-card__header">
                                <span class="balance-card__currency">${info.currency}</span>
                                <span class="balance-card__status ${availableClass}">${isAvailable}</span>
                            </div>
                            <div class="balance-card__total">${info.total_balance}</div>
                            <div class="balance-card__detail">
                                <span>赠金 <b>${info.granted_balance}</b></span>
                                <span>充值 <b>${info.topped_up_balance}</b></span>
                            </div>
                        </div>
                    `;
                });
                html += '</div>';
                resultDiv.innerHTML = html;
            } else {
                resultDiv.innerHTML = '<div class="balance-empty">暂无余额信息</div>';
            }
        })
        .catch(err => {
            resultDiv.innerHTML = `<div class="balance-error">请求失败: ${err.message}</div>`;
        });
}

// ---------- 认证状态 ----------
function loadAuthStatus() {
    fetch('/admin/auth/status')
        .then(res => res.json())
        .then(data => {
            if (data.password_mode === 'persistent') {
                document.getElementById('pwdMode').textContent = '已持久化';
                document.getElementById('pwdModeDetail').textContent = '密码已保存到数据库，重启后仍然有效';
            } else {
                document.getElementById('pwdMode').textContent = '临时密码';
                document.getElementById('pwdModeDetail').textContent = '当前为临时密码，仅本次运行有效。修改后即永久保存。';
            }
        })
        .catch(err => console.error(err));
}

function changePassword() {
    const oldPwd = document.getElementById('oldPwd').value;
    const newPwd = document.getElementById('newPwd').value;
    const msgDiv = document.getElementById('pwdMsg');

    if (!oldPwd || !newPwd || newPwd.length < 6) {
        msgDiv.innerHTML = '<span style="color:#d32f2f;">旧密码和新密码（至少6位）为必填项</span>';
        return;
    }

    fetch('/admin/change_password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({old_password: oldPwd, new_password: newPwd})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            msgDiv.innerHTML = '<span style="color:#d32f2f;">' + (data.error.message || data.error) + '</span>';
        } else {
            msgDiv.innerHTML = '<span style="color:#28a745;">' + data.message + '</span>';
            document.getElementById('oldPwd').value = '';
            document.getElementById('newPwd').value = '';
            loadAuthStatus();
        }
    })
    .catch(err => msgDiv.innerHTML = '<span style="color:#d32f2f;">请求失败: ' + err.message + '</span>');
}

// ---------- 定价管理 ----------
let pricingConfig = null;

function updatePricingMode() {
    if (!pricingConfig) return;
    const official = document.getElementById('pricingMode').value === 'peak_valley';
    // 缓存未保存的固定单价，来回切换不会丢失编辑。
    if (document.getElementById('pricingTableBody').dataset.mode === 'fixed') {
        pricingConfig.fixed = collectPricingRows();
    }
    const tbody = document.getElementById('pricingTableBody');
    tbody.innerHTML = '';
    tbody.dataset.mode = official ? 'peak_valley' : 'fixed';
    Object.entries(official ? pricingConfig.peak : pricingConfig.fixed).forEach(([model, prices]) => {
        addPricingRow(model, prices);
    });
    tbody.querySelectorAll('input, button').forEach(el => el.disabled = official);
    document.querySelectorAll('.pricing-add input, .pricing-add button').forEach(el => el.disabled = official);
    document.getElementById('pricingPeriod').textContent = official
        ? '下表展示官方高峰价，空闲价为下表的一半。保存后启用。'
        : '全天使用下表固定单价。保存后启用。';
}

function loadPricing() {
    fetch('/admin/pricing')
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showPricingMsg(data.error.message || '加载失败', 'error');
                return;
            }
            pricingConfig = data;
            document.getElementById('pricingMode').value = data.mode;
            document.getElementById('pricingStatus').textContent = data.mode === 'peak_valley'
                ? '官方峰谷 · ' + (data.period === 'peak' ? '当前高峰' : '当前空闲')
                : (data.is_default ? '默认固定定价' : '自定义固定定价');
            const tbody = document.getElementById('pricingTableBody');
            tbody.innerHTML = '';
            delete tbody.dataset.mode;
            updatePricingMode();
        })
        .catch(err => showPricingMsg('加载失败: ' + err.message, 'error'));
}

function addPricingRow(modelName = '', prices = null) {
    const tbody = document.getElementById('pricingTableBody');
    const modelInput = document.getElementById('newModelName');
    const hitInput = document.getElementById('newInputHit');
    const missInput = document.getElementById('newInputMiss');
    const outInput = document.getElementById('newOutput');

    const name = modelName || modelInput.value.trim();
    if (!name) {
        alert('请输入模型名称');
        return;
    }

    const hit = prices ? prices.input_hit : parseFloat(hitInput.value) || 0;
    const miss = prices ? prices.input_miss : parseFloat(missInput.value) || 0;
    const out = prices ? prices.output : parseFloat(outInput.value) || 0;

    if (Array.from(tbody.rows).some(row => row.dataset.model === name)) {
        alert('该模型已存在，请直接修改对应行');
        return;
    }

    const tr = document.createElement('tr');
    tr.setAttribute('data-model', name);
    tr.innerHTML = `
        <td><span class="model-name"></span></td>
        <td><input type="number" class="p-hit" value="${hit}" step="0.001" min="0"></td>
        <td><input type="number" class="p-miss" value="${miss}" step="0.001" min="0"></td>
        <td><input type="number" class="p-out" value="${out}" step="0.001" min="0"></td>
        <td><button class="btn-del" onclick="removePricingRow(this)">移除</button></td>
    `;
    tr.querySelector('.model-name').textContent = name;
    tbody.appendChild(tr);

    modelInput.value = '';
    hitInput.value = '';
    missInput.value = '';
    outInput.value = '';
}

function removePricingRow(btn) {
    btn.closest('tr').remove();
}

function collectPricingRows() {
    const rows = document.querySelectorAll('#pricingTableBody tr');
    const models = {};
    rows.forEach(tr => {
        const name = tr.getAttribute('data-model');
        if (!name) return;
        models[name] = {
            input_hit: parseFloat(tr.querySelector('.p-hit').value) || 0,
            input_miss: parseFloat(tr.querySelector('.p-miss').value) || 0,
            output: parseFloat(tr.querySelector('.p-out').value) || 0
        };
    });

    return models;
}

function savePricing() {
    const mode = document.getElementById('pricingMode').value;
    const models = mode === 'fixed' ? collectPricingRows() : null;
    fetch('/admin/pricing', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mode, ...(models === null ? {} : {models})})
    })
    .then(res => res.json())
    .then(data => {
        if (data.error || data.detail) {
            showPricingMsg('保存失败: ' + (data.error ? (data.error.message || data.error) : JSON.stringify(data.detail)), 'error');
        } else {
            showPricingMsg(mode === 'fixed' ? '固定定价已保存' : '已启用官方峰谷计费');
            loadPricing();
        }
    })
    .catch(err => showPricingMsg('保存失败: ' + err.message, 'error'));
}

function resetPricing() {
    if (!confirm('确定恢复默认定价吗？自定义配置将被清除。')) return;
    fetch('/admin/pricing', {method: 'DELETE'})
        .then(res => res.json())
        .then(data => {
            if (data.error) {
                showPricingMsg('恢复失败: ' + (data.error.message || data.error), 'error');
            } else {
                showPricingMsg('已恢复默认定价');
                loadPricing();
            }
        })
        .catch(err => showPricingMsg('恢复失败: ' + err.message, 'error'));
}

// ---------- 背景配置 ----------
function loadBackground() {
    fetch('/admin/background')
        .then(res => res.json())
        .then(data => {
            if (data.enabled) {
                document.documentElement.style.setProperty('--background-image', `url("${data.url}")`);
                document.body.classList.add('background-enabled');
            } else {
                document.body.classList.remove('background-enabled');
            }
        })
        .catch(err => console.error('背景配置加载失败:', err));
}

// ---------- 自动刷新 ----------
document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        loadKeys();
        loadUpstreamStatus();
    }
});
window.addEventListener('focus', function() {
    loadKeys();
    loadUpstreamStatus();
});

// ---------- 启动加载 ----------
document.addEventListener('DOMContentLoaded', function() {
    loadBackground();
});

loadKeys();
loadUpstreamStatus();
loadPricing();
loadAuthStatus();
