// =========================================================
// BUKABOX Dashboard v4.3-Sync — main.js (hardening)
// =========================================================

// --- boot log (cek apakah file benar2 termuat) ---
console.log("✅ main.js loaded (ts:", Date.now(), ")");

// ---------- FORMATTER UANG ----------
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("input.money").forEach(inp => {
    inp.addEventListener("input", () => {
      const pos = inp.selectionStart ?? inp.value.length;
      const val = (inp.value || "").replace(/\D/g, "");
      const fmt = val.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
      inp.value = fmt;
      try {
        const newPos = Math.min(fmt.length, pos + (fmt.length - val.length));
        inp.setSelectionRange(newPos, newPos);
      } catch (_) {}
    });
    const form = inp.closest("form");
    if (form) {
      form.addEventListener("submit", () => {
        inp.value = (inp.value || "").replace(/\./g, "");
      });
    }
  });
});

// =========================================================
//  KALKULATOR OTOMATIS — AMAN UNTUK SEMUA ASSET CLASS
// =========================================================

// ===== Helpers =====
function toNumberSafe(value) {
  if (!value) return 0;
  let clean = value.replace(/[^\d.,-]/g, '');
  if (clean.includes('.') && clean.includes(',')) clean = clean.replace(/\./g, '').replace(',', '.');
  else if (clean.includes(',')) clean = clean.replace(',', '.');
  else clean = clean.replace(/\./g, '');
  const num = Number(clean);
  return isNaN(num) ? 0 : num;
}
function delayedCalc(fn){ clearTimeout(window._calcTimer); window._calcTimer = setTimeout(fn, 20); }

// ===== Crypto =====
window.calcCryptoAmount = function() {
  delayedCalc(() => {
    const idr   = toNumberSafe(document.getElementById('crypto_idr')?.value);
    const price = toNumberSafe(document.getElementById('crypto_price')?.value);
    const out   = document.getElementById('crypto_total');
    if (!out) return;
    out.value = price > 0 ? (idr / price).toFixed(6) : 0;
  });
};

// ===== Gold (gram) =====
window.calcGoldGram = function() {
  delayedCalc(() => {
    const idr   = toNumberSafe(document.getElementById('gold_idr')?.value);
    const price = toNumberSafe(document.getElementById('gold_price')?.value);
    const out   = document.getElementById('gold_total');
    if (!out) return;
    out.value = price > 0 ? (idr / price).toFixed(2) : 0;
  });
};

// ===== Stock (lot) =====
window.calcStockLot = function() {
  delayedCalc(() => {
    const idr   = toNumberSafe(document.getElementById('stock_idr')?.value);
    const price = toNumberSafe(document.getElementById('stock_price')?.value);
    const out   = document.getElementById('stock_total');
    if (!out) return;
    out.value = price > 0 ? (idr / (price * 100)).toFixed(2) : 0;
  });
};

// ===== Land (IDR total) =====
window.calcLandValue = function() {
  delayedCalc(() => {
    const ubin  = toNumberSafe(document.getElementById('land_ubin')?.value);
    const price = toNumberSafe(document.getElementById('land_price')?.value);
    const out   = document.getElementById('land_total');
    if (!out) return;
    out.value = (ubin * price).toFixed(0);
  });
};

// Autobind opsional (kalau tidak pakai oninput=...)
document.addEventListener("input", (e) => {
  const id = e.target?.id;
  if (id === "crypto_idr" || id === "crypto_price") window.calcCryptoAmount();
  if (id === "gold_idr"   || id === "gold_price")   window.calcGoldGram();
  if (id === "stock_idr"  || id === "stock_price")  window.calcStockLot();
  if (id === "land_ubin"  || id === "land_price")   window.calcLandValue();
});


// ---------- TOGGLE & TAB (GLOBAL) ----------
window.toggleDetail = function(id) {
  const el = document.getElementById(id);
  if (!el) {
    console.warn("toggleDetail: element not found:", id);
    return;
  }
  el.classList.toggle("open");
};

function openDetail(t) {
  document.querySelectorAll('.tab-content').forEach(e => e.classList.remove('active'));
  const el = document.getElementById(t + '-detail');
  if (el) el.classList.add('active');
  document.getElementById('asset-detail').scrollIntoView({ behavior: 'smooth' });
}

// =========================================================
// CHART.JS — hanya jalan jika Chart ada & data tersedia
// =========================================================
const commonOpt = {
  responsive: true,
  maintainAspectRatio: true,
  aspectRatio: 1,
  plugins: {
    legend: { position: 'bottom', labels: { font: { size: 13 }, color: '#333' } },
    tooltip: {
      callbacks: {
        label: function (ctx) {
          const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
          const val = Number(ctx.raw || 0);
          const percent = total > 0 ? ((val / total) * 100).toFixed(1) : '0.0';
          return `${ctx.label}: Rp ${val.toLocaleString('id-ID')} (${percent}%)`;
        }
      }
    }
  }
};

function initChartsSafely() {
  if (typeof Chart === "undefined") {
    console.warn("Chart.js belum termuat; lewati init chart.");
    return;
  }

  // Income
  try {
    const el = document.getElementById('incomeChart');
    const d = window.BUKABOX_DATA?.income;
    if (el && d?.labels && d?.data) {
      new Chart(el, {
        type: 'doughnut',
        data: {
          labels: d.labels,
          datasets: [{ data: d.data, backgroundColor: ['#B8E4C9','#A5C8E4','#F4C7B8','#EAD1DC'], cutout: '60%' }]
        },
        options: commonOpt
      });
    }
  } catch (err) { console.error("Income chart error:", err); }

  // Cashflow
  try {
    const el = document.getElementById('cashflowChart');
    const t = window.BUKABOX_DATA?.totals;
    if (el && t) {
      new Chart(el, {
        type: 'pie',
        data: {
          labels: ['Income','Expense','Investment','Buffer'],
          datasets: [{ data: [t.total_income, t.total_expense, t.total_invest_month, t.buffer_balance],
                       backgroundColor: ['#A5C8E4','#F4C7B8','#B8E4C9','#C6E2B3'] }]
        },
        options: commonOpt
      });
    }
  } catch (err) { console.error("Cashflow chart error:", err); }

  // Investment
  try {
    const el = document.getElementById('investChart');
    const i = window.BUKABOX_DATA?.investment;
    if (el && i) {
      new Chart(el, {
        type: 'doughnut',
        data: {
          labels: ['Crypto','Gold','Land','Business','Stock'],
          datasets: [{ data: [i.inv_crypto, i.inv_gold, i.inv_land, i.inv_business, i.inv_stock],
                       backgroundColor: ['#B8E4C9','#FCE0A2','#D7BCE8','#F4C7B8','#A5C8E4'],
                       cutout: '60%' }]
        },
        options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { position: 'bottom' } } }
      });
    }
  } catch (err) { console.error("Investment chart error:", err); }
}

// jalankan chart init setelah DOM siap (dan biasanya setelah BUKABOX_DATA didefinisikan di HTML)
document.addEventListener("DOMContentLoaded", initChartsSafely);

// marker siap
window.BUKABOX_OK = true;
console.log("✅ main.js ready; globals:", {
  hasToggle: typeof window.toggleDetail === 'function',
  hasOpen: typeof window.openDetail === 'function'
  
});
