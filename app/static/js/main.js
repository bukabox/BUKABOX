/* ==========================================================
   BUKABOX DASHBOARD SCRIPT v4.6 (Cleaned & Stable)
   ========================================================== */

/* ----------------------- Format Uang ----------------------- */
document.addEventListener("DOMContentLoaded", () => {

  // Format angka otomatis pakai titik ribuan
  document.querySelectorAll("input.money").forEach(inp => {
    inp.addEventListener("input", () => {
      const pos = inp.selectionStart;
      const val = inp.value.replace(/\D/g, "");
      const fmt = val.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
      inp.value = fmt;
      const newPos = pos + (fmt.length - val.length);
      inp.setSelectionRange(newPos, newPos);
    });

    const form = inp.closest("form");
    if (form) {
      form.addEventListener("submit", () => {
        inp.value = inp.value.replace(/\./g, "");
      });
    }
  });

  /* -------------------- Parse & Hitung Angka -------------------- */
  const parseNumber = str => {
    if (!str) return 0;
    return parseFloat(str.toString().replace(/\./g, '').replace(',', '.')) || 0;
  };

  const calcCryptoAmount = () => {
    const idr = parseNumber(document.getElementById('crypto_idr')?.value);
    const price = parseNumber(document.getElementById('crypto_price')?.value);
    const el = document.getElementById('crypto_total');
    if (el) el.value = price > 0 ? (idr / price).toFixed(6) : 0;
  };

  const calcGoldGram = () => {
    const idr = parseNumber(document.getElementById('gold_idr')?.value);
    const price = parseNumber(document.getElementById('gold_price')?.value);
    const gram = price > 0 ? idr / price : 0;
    const el = document.getElementById('gold_total');
    if (el) el.value = gram.toFixed(2);
  };

  const calcStockLot = () => {
    const idr = parseNumber(document.getElementById('stock_idr')?.value);
    const price = parseNumber(document.getElementById('stock_price')?.value);
    const el = document.getElementById('stock_total');
    if (el) el.value = price > 0 ? (idr / (price * 100)).toFixed(2) : 0;
  };

  const calcLandValue = () => {
    const ubin = parseNumber(document.getElementById('land_ubin')?.value);
    const price = parseNumber(document.getElementById('land_price')?.value);
    const total = ubin * price;
    const el = document.getElementById('land_total');
    if (el) el.value = total > 0 ? total.toLocaleString('id-ID') : 0;
  };
 
  /* -------------------- Event Binding -------------------- */
  const bindBlur = (ids, fn) => ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('blur', fn);
  });

  bindBlur(['crypto_idr', 'crypto_price'], calcCryptoAmount);
  bindBlur(['gold_idr', 'gold_price'], calcGoldGram);
  bindBlur(['stock_idr', 'stock_price'], calcStockLot);
  bindBlur(['land_ubin', 'land_price'], calcLandValue);

  /* -------------------- Masonry Layout -------------------- */
  const cols = [document.getElementById("col1"), document.getElementById("col2")];
  const cards = Array.from(document.querySelectorAll("section.card"));
  if (cols[0] && cols[1]) {
    if (window.innerWidth < 900) {
      const container = document.getElementById("cardContainer");
      cards.forEach(card => container.appendChild(card));
    } else {
      cards.forEach(card => {
        const shorter = cols.reduce((a, b) => a.offsetHeight < b.offsetHeight ? a : b);
        shorter.appendChild(card);
      });
    }
  }

  /* -------------------- Navbar Burger Toggle -------------------- */
  const btn = document.getElementById('navToggle');
  const menu = document.getElementById('navMenu');
  if (btn && menu) {
    const closeMenu = () => {
      menu.classList.remove('open');
      btn.setAttribute('aria-expanded', 'false');
    };
    btn.addEventListener('click', () => {
      const isOpen = menu.classList.toggle('open');
      btn.setAttribute('aria-expanded', String(isOpen));
    });
    document.addEventListener('click', e => {
      if (!menu.contains(e.target) && !btn.contains(e.target)) closeMenu();
    });
    window.addEventListener('resize', () => {
      if (window.innerWidth > 900) closeMenu();
    });
  }

  /* -------------------- Chart.js Options -------------------- */
  const commonOpt = {
    responsive: true,
    maintainAspectRatio: true,
    aspectRatio: 1,
    plugins: {
      legend: { position: 'bottom', labels: { font: { size: 13 }, color: '#333' } },
      tooltip: {
        callbacks: {
          label: function (context) {
            const dataset = context.dataset;
            const total = dataset.data.reduce((a, b) => a + b, 0);
            const val = dataset.data[context.dataIndex];
            const percent = total > 0 ? ((val / total) * 100).toFixed(1) : 0;
            const formatted = val.toLocaleString('id-ID');
            return `${context.label}: Rp ${formatted} (${percent}%)`;
          }
        }
      }
    }
  };
  /* -------------------- Plugin: No Data Text -------------------- */
Chart.register({
  id: 'noDataText',
  afterDraw(chart) {
    const total = chart.data.datasets[0].data.reduce((a, b) => a + b, 0);
    if (total === 1 && chart.data.labels[0] === 'Belum ada data') {
      const { ctx, chartArea: { left, top, width, height } } = chart;
      ctx.save();
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#888';
      ctx.font = '14px sans-serif';
      ctx.fillText('Belum ada data', left + width / 2, top + height / 2);
      ctx.restore();
    }
  }
});
  /* -------------------- CASHFLOW CHART -------------------- */
  const cashCtx = document.getElementById("cashflowChart");
  if (cashCtx) {
    const data = [
      parseFloat(cashCtx.dataset.income || 0),
      parseFloat(cashCtx.dataset.expense || 0),
      parseFloat(cashCtx.dataset.invest || 0),
      parseFloat(cashCtx.dataset.buffer || 0)
    ];
    const total = data.reduce((a, b) => a + b, 0);
    if (total === 0) {
      new Chart(cashCtx, {
        type: "pie",
        data: { labels: ["Belum ada data"], datasets: [{ data: [1], backgroundColor: ["#e0e0e0"] }] },
        options: { plugins: { legend: { display: false }, tooltip: { enabled: false } } }
      });
    } else {
      new Chart(cashCtx, {
        type: "pie",
        data: {
          labels: ["Income", "Expense", "Investment", "Buffer"],
          datasets: [{ data, backgroundColor: ["#A5C8E4","#F4C7B8","#B8E4C9","#C6E2B3"] }]
        },
        options: commonOpt
      });
    }
  }

  /* -------------------- INCOME CHART -------------------- */
  const incomeCtx = document.getElementById('incomeChart');
  if (incomeCtx) {
    const labels = (incomeCtx.dataset.labels || "").split(",");
    const values = (incomeCtx.dataset.values || "").split(",").map(parseFloat);
    const total = values.reduce((a, b) => a + b, 0);
    if (labels.length === 0 || total === 0) {
      new Chart(incomeCtx, {
        type: 'doughnut',
        data: { labels: ['Belum ada data'], datasets: [{ data: [1], backgroundColor: ['#d9d9d9'], cutout: '60%' }] },
        options: { cutout: '60%', plugins: { legend: { display: false }, tooltip: { enabled: false } } }
      });
    } else {
      new Chart(incomeCtx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: ['#B8E4C9','#A5C8E4','#F4C7B8','#EAD1DC'], cutout: '60%' }] },
        options: commonOpt
      });
    }
  }

  /* -------------------- INVESTMENT CHART -------------------- */
  /* -------------------- INVESTMENT CHART -------------------- */
const investCtx = document.getElementById("investChart");
if (investCtx) {
  const data = [
    parseFloat(investCtx.dataset.crypto || 0),
    parseFloat(investCtx.dataset.gold || 0),
    parseFloat(investCtx.dataset.land || 0),
    parseFloat(investCtx.dataset.business || 0),
    parseFloat(investCtx.dataset.stock || 0),
    parseFloat(investCtx.dataset.emergency || 0) // 🟩 tambahkan dana darurat
  ];

  const total = data.reduce((a, b) => a + b, 0);
  if (total === 0) {
    new Chart(investCtx, {
      type: "doughnut",
      data: { labels: ["Belum ada data"], datasets: [{ data: [1], backgroundColor: ["#d9d9d9"] }] },
      options: { cutout: "60%", plugins: { legend: { display: false }, tooltip: { enabled: false } } }
    });
  } else {
    new Chart(investCtx, {
      type: "doughnut",
      data: {
        labels: ["Crypto", "Gold", "Land", "Business", "Stock", "Emergency Fund"], // 🟩 tambahkan label baru
        datasets: [{
          data,
          backgroundColor: [
            "#B8E4C9", // Crypto
            "#FCE0A2", // Gold
            "#D7BCE8", // Land
            "#F4C7B8", // Business
            "#A5C8E4", // Stock
            "#AED6F1"  // 🟩 Emergency Fund
          ],
          cutout: "60%"
        }]
      },
      options: commonOpt
    });
  }
}

  /* -------------------- Toggle Detail Cashflow -------------------- */
  window.toggleDetail = function(id) {
    const box = document.getElementById(id);
    if (!box) return;
    box.classList.toggle('open');
    // Scroll agar tabel terlihat penuh saat dibuka
    if (box.classList.contains('open')) {
      box.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };
/* ======================= DETAIL TOGGLER ======================= */
  function toggleDetail(id) {
    document.getElementById(id).classList.toggle("open");
  }
  function openDetail(t) {
    document.querySelectorAll('.tab-content').forEach(e => e.classList.remove('active'));
    const el = document.getElementById(t + '-detail');
    if (el) el.classList.add('active');
    document.getElementById('asset-detail').scrollIntoView({ behavior: 'smooth' });
  }

}); // END DOMContentLoaded
