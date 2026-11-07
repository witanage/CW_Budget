/*
 * Offline transaction queue.
 *
 * Loaded by pages (<script>) and by the service worker (importScripts) so there
 * is a single implementation of "store locally, replay when online".
 *
 * - New transactions entered while offline (or when the request fails to reach
 *   the server) are stored in IndexedDB.
 * - They are replayed to POST /api/transactions in the order they were made,
 *   when the browser comes back online, when the page opens/regains focus, via
 *   Background Sync where supported, and on a manual "Sync now".
 * - Every entry carries a client_request_id; the server uses it to ignore
 *   duplicates if a replay is retried after the response was lost.
 * - Only plain JSON transactions are queued (no photo attachments).
 */
(function (root) {
  'use strict';

  var DB_NAME = 'cw-offline';
  var STORE = 'transactions';
  var SYNC_TAG = 'sync-transactions';
  var LOCK_NAME = 'cw-offline-flush';
  var inPage = typeof document !== 'undefined';

  // ---------------------------------------------------------------- storage

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = root.indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        var db = req.result;
        if (!db.objectStoreNames.contains(STORE)) {
          db.createObjectStore(STORE, { keyPath: 'id' });
        }
      };
      req.onsuccess = function () { resolve(req.result); };
      req.onerror = function () { reject(req.error); };
    });
  }

  function withStore(mode, fn) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, mode);
        var result = fn(tx.objectStore(STORE));
        tx.oncomplete = function () { db.close(); resolve(result && result.result !== undefined ? result.result : result); };
        tx.onerror = tx.onabort = function () { db.close(); reject(tx.error); };
      });
    });
  }

  function uuid() {
    if (root.crypto && root.crypto.randomUUID) return root.crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  function localDate() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return d.getFullYear() + '-' + m + '-' + day;
  }

  function list() {
    return withStore('readonly', function (s) { return s.getAll(); }).then(function (rows) {
      return (rows || []).sort(function (a, b) { return a.queuedAt - b.queuedAt; });
    });
  }

  function put(entry) { return withStore('readwrite', function (s) { s.put(entry); }); }
  function discard(id) {
    return withStore('readwrite', function (s) { s.delete(id); }).then(notifyChange);
  }

  function counts() {
    return list().then(function (rows) {
      var failed = rows.filter(function (r) { return r.state === 'failed'; }).length;
      return { pending: rows.length - failed, failed: failed, total: rows.length };
    });
  }

  // ---------------------------------------------------------------- enqueue

  /**
   * Queue a transaction payload. The payload keeps the user-visible fields
   * (description, debit, credit, ... year, month). The entry date is captured
   * now so the transaction is not re-dated to the sync time.
   */
  function enqueue(payload) {
    var data = Object.assign({}, payload);
    data.client_request_id = data.client_request_id || uuid();
    data.transaction_date = data.transaction_date || localDate();
    var entry = {
      id: data.client_request_id,
      queuedAt: Date.now(),
      state: 'pending',
      attempts: 0,
      error: null,
      payload: data
    };
    return put(entry).then(function () {
      notifyChange();
      registerBackgroundSync();
      return entry;
    });
  }

  // ------------------------------------------------------------------ flush

  function looksLikeLoginRedirect(response) {
    var type = response.headers.get('content-type') || '';
    return response.redirected || response.status === 401 || response.status === 403 ||
      type.indexOf('json') === -1;
  }

  function sendOne(entry) {
    return fetch('/api/transactions', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(entry.payload)
    }).then(function (response) {
      if (response.ok && !looksLikeLoginRedirect(response)) return { outcome: 'synced' };
      if (looksLikeLoginRedirect(response)) return { outcome: 'auth' };
      if (response.status === 429 || response.status >= 500) return { outcome: 'retry' };
      // Other 4xx: the server rejected this entry, retrying will not help.
      return response.json().catch(function () { return {}; }).then(function (body) {
        return { outcome: 'rejected', error: body.error || ('Server rejected the transaction (' + response.status + ')') };
      });
    }).catch(function () {
      return { outcome: 'retry' };   // network failure: still offline
    });
  }

  function doFlush() {
    var summary = { synced: 0, failed: 0, remaining: 0, authRequired: false };
    return list().then(function (rows) {
      var queue = rows.filter(function (r) { return r.state !== 'failed'; });
      var chain = Promise.resolve(true);
      queue.forEach(function (entry) {
        chain = chain.then(function (keepGoing) {
          if (!keepGoing) return false;
          entry.attempts += 1;
          return sendOne(entry).then(function (res) {
            if (res.outcome === 'synced') {
              summary.synced += 1;
              return withStore('readwrite', function (s) { s.delete(entry.id); }).then(function () { return true; });
            }
            if (res.outcome === 'rejected') {
              summary.failed += 1;
              entry.state = 'failed';
              entry.error = res.error;
              return put(entry).then(function () { return true; });
            }
            if (res.outcome === 'auth') summary.authRequired = true;
            return put(entry).then(function () { return false; });   // stop, keep order, retry later
          });
        });
      });
      return chain;
    }).then(function () {
      return counts();
    }).then(function (c) {
      summary.remaining = c.pending;
      return summary;
    });
  }

  var flushing = null;

  /** Replay queued transactions. Safe to call from several places at once. */
  function flush() {
    if (flushing) return flushing;
    var run = function () { return doFlush(); };
    var nav = root.navigator;
    flushing = (nav && nav.locks && nav.locks.request
      ? nav.locks.request(LOCK_NAME, run)   // also serialises page vs. service worker
      : run()
    ).then(function (summary) {
      flushing = null;
      notifyChange();
      if (summary.synced > 0) notifySynced(summary);
      return summary;
    }, function (err) {
      flushing = null;
      throw err;
    });
    return flushing;
  }

  function registerBackgroundSync() {
    if (!inPage || !root.navigator.serviceWorker) return;
    root.navigator.serviceWorker.ready.then(function (reg) {
      if (reg.sync) return reg.sync.register(SYNC_TAG);
    }).catch(function () { /* unsupported: the online/focus triggers still work */ });
  }

  // ----------------------------------------------------------------- events

  function notifyChange() {
    if (inPage) {
      root.dispatchEvent(new CustomEvent('offlinequeue:change'));
    } else if (root.clients) {
      root.clients.matchAll({ includeUncontrolled: true }).then(function (cs) {
        cs.forEach(function (c) { c.postMessage({ type: 'OFFLINE_QUEUE_CHANGED' }); });
      });
    }
  }

  function notifySynced(summary) {
    if (inPage) {
      root.dispatchEvent(new CustomEvent('offlinequeue:synced', { detail: summary }));
    } else if (root.clients) {
      root.clients.matchAll({ includeUncontrolled: true }).then(function (cs) {
        cs.forEach(function (c) { c.postMessage({ type: 'OFFLINE_QUEUE_SYNCED', summary: summary }); });
      });
    }
  }

  // --------------------------------------------------------------------- UI

  function esc(s) {
    var d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function initUi() {
    var pill = document.createElement('button');
    pill.type = 'button';
    pill.id = 'offline-queue-pill';
    pill.style.cssText = 'position:fixed;left:16px;bottom:16px;z-index:1060;display:none;border:0;' +
      'border-radius:999px;padding:10px 16px;font-size:14px;color:#fff;box-shadow:0 4px 12px rgba(0,0,0,.3);cursor:pointer;';
    document.body.appendChild(pill);

    var panel = document.createElement('div');
    panel.id = 'offline-queue-panel';
    panel.style.cssText = 'position:fixed;left:16px;bottom:64px;z-index:1060;display:none;max-width:min(92vw,380px);' +
      'max-height:50vh;overflow:auto;background:#fff;color:#222;border-radius:12px;padding:12px;' +
      'box-shadow:0 8px 24px rgba(0,0,0,.35);font-size:14px;';
    document.body.appendChild(panel);

    function money(p) {
      var v = p.credit || p.debit;
      return v ? Number(v).toFixed(2) : '';
    }

    function renderPanel() {
      return list().then(function (rows) {
        if (!rows.length) { panel.style.display = 'none'; return; }
        panel.innerHTML = '<div style="font-weight:600;margin-bottom:8px;">Saved on this device</div>' +
          rows.map(function (r) {
            var failed = r.state === 'failed';
            return '<div style="border-top:1px solid #eee;padding:6px 0;">' +
              '<div><strong>' + esc(r.payload.description) + '</strong> ' + esc(money(r.payload)) +
              ' <span style="color:#888;">' + esc(r.payload.transaction_date) + '</span></div>' +
              (failed ? '<div style="color:#c0392b;">Not accepted: ' + esc(r.error) + '</div>'
                      : '<div style="color:#888;">Waiting to sync' + (r.attempts ? ' (tried ' + r.attempts + 'x)' : '') + '</div>') +
              (failed ? '<button data-discard="' + esc(r.id) + '" style="margin-top:4px;" class="btn btn-sm btn-outline-danger">Discard</button>' : '') +
              '</div>';
          }).join('') +
          '<div style="margin-top:8px;"><button id="offline-sync-now" class="btn btn-sm btn-primary">Sync now</button></div>';
      });
    }

    function refresh() {
      counts().then(function (c) {
        var offline = !root.navigator.onLine;
        if (!c.total && !offline) { pill.style.display = 'none'; panel.style.display = 'none'; return; }
        pill.style.display = 'block';
        if (c.failed) {
          pill.style.background = '#c0392b';
          pill.textContent = c.failed + ' not synced - review';
        } else if (c.pending) {
          pill.style.background = offline ? '#6c757d' : '#e67e22';
          pill.textContent = (offline ? 'Offline - ' : '') + c.pending + ' waiting to sync';
        } else {
          pill.style.background = '#6c757d';
          pill.textContent = 'Offline';
        }
        if (panel.style.display !== 'none') renderPanel();
      }).catch(function () { /* IndexedDB unavailable: stay hidden */ });
    }

    pill.addEventListener('click', function () {
      if (panel.style.display === 'none') {
        renderPanel().then(function () { panel.style.display = 'block'; });
      } else {
        panel.style.display = 'none';
      }
    });

    panel.addEventListener('click', function (e) {
      var d = e.target.getAttribute && e.target.getAttribute('data-discard');
      if (d) { discard(d).then(renderPanel); return; }
      if (e.target.id === 'offline-sync-now') {
        e.target.disabled = true;
        flush().then(function (s) {
          if (s.authRequired && typeof showToast === 'function') showToast('Please log in again to sync', 'warning');
          renderPanel();
        });
      }
    });

    root.addEventListener('offlinequeue:change', refresh);
    root.addEventListener('online', refresh);
    root.addEventListener('offline', refresh);
    refresh();
  }

  function initPage() {
    initUi();

    root.addEventListener('offlinequeue:synced', function (e) {
      var n = e.detail && e.detail.synced;
      if (typeof showToast === 'function') {
        showToast(n + ' offline transaction' + (n === 1 ? '' : 's') + ' synced', 'success');
      }
      if (typeof loadTransactions === 'function') loadTransactions();
      if (typeof loadSidebarWidgets === 'function') loadSidebarWidgets();
    });

    function tryFlush() {
      if (!root.navigator.onLine) return;
      counts().then(function (c) {
        if (c.pending) return flush().then(function (s) {
          if (s.authRequired && typeof showToast === 'function') {
            showToast('Offline transactions are waiting. Log in again to sync them.', 'warning');
          }
        });
      }).catch(function () {});
    }

    root.addEventListener('online', tryFlush);
    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible') tryFlush();
    });
    setInterval(tryFlush, 60000);
    tryFlush();

    // Changes made by the service worker's background sync
    if (root.navigator.serviceWorker) {
      root.navigator.serviceWorker.addEventListener('message', function (e) {
        var msg = e.data || {};
        if (msg.type === 'OFFLINE_QUEUE_CHANGED') root.dispatchEvent(new CustomEvent('offlinequeue:change'));
        if (msg.type === 'OFFLINE_QUEUE_SYNCED') root.dispatchEvent(new CustomEvent('offlinequeue:synced', { detail: msg.summary }));
      });
    }
  }

  root.OfflineQueue = {
    enqueue: enqueue,
    flush: flush,
    list: list,
    counts: counts,
    discard: discard,
    newId: uuid,
    isSupported: !!root.indexedDB,
    SYNC_TAG: SYNC_TAG
  };

  if (inPage && root.indexedDB) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initPage);
    else initPage();
  }
})(self);
