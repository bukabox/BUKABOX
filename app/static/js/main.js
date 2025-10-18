/* ==========================================================
   BUKABOX DASHBOARD SCRIPT v4.6 (Cleaned & Stable)
   ========================================================== */
/* ==========================================================
   GLOBAL CHART CONFIG (berlaku untuk semua doughnut)
   ========================================================== */
Chart.defaults.datasets.doughnut.cutout = '90%';
Chart.defaults.datasets.doughnut.borderWidth = 2;
Chart.defaults.datasets.doughnut.borderColor = '#f6f9ff';
Chart.defaults.plugins.legend.position = 'bottom';
Chart.defaults.plugins.legend.labels.boxWidth = 14;
Chart.defaults.plugins.legend.labels.color = '#333';
Chart.defaults.plugins.legend.labels.font = { family: 'Poppins', size: 13 };
Chart.defaults.plugins.tooltip.backgroundColor = '#fff';
Chart.defaults.plugins.tooltip.titleColor = '#333';
Chart.defaults.plugins.tooltip.bodyColor = '#555';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.borderColor = '#eee';
Chart.defaults.plugins.tooltip.padding = 8;

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

  // 💡 di Chart.js v4, letakkan di level teratas (bukan di dataset)
  cutout: '70%',   // semakin besar = ring makin tipis
  radius: '98%',   // ukuran luar chart
  layout: { padding: 5 },

  plugins: {
    legend: {
      position: 'bottom',
      labels: {
        font: { size: 13, family: 'Poppins' },
        color: '#333',
        boxWidth: 14
      }
    },
    tooltip: {
      backgroundColor: '#fff',
      titleColor: '#333',
      bodyColor: '#555',
      borderWidth: 1,
      borderColor: '#eee',
      padding: 8,
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
  },

  elements: {
    arc: {
      borderWidth: 2,
      borderColor: '#f6f9ff' // efek outline lembut
    }
  },

  animation: {
    duration: 600,
    easing: 'easeOutQuart'
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
        type: "doughnut",
        data: { labels: ["Belum ada data"], datasets: [{ data: [1], backgroundColor: ["#7e7e7eff"] }] },
        options: { plugins: { legend: { display: false }, tooltip: { enabled: false } } }
      });
    } else {
      new Chart(cashCtx, {
        type: "doughnut",
        data: {
          labels: ["Income", "Expense", "Investment", "Buffer"],
          datasets: [{ data, backgroundColor: ["#44acf2","#f1905e","#a5e260","#a9e157"] }]
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
        data: { labels: ['Belum ada data'], datasets: [{ data: [1], backgroundColor: ['#949393ff'], cutout: '70%' }] },
        options: { cutout: '70%', plugins: { legend: { display: false }, tooltip: { enabled: false } } }
      });
    } else {
      new Chart(incomeCtx, {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: ['#57d989','#44acf2','#f1905e','#e869a0ff'], cutout: '70%' }] },
        options: commonOpt
      });
    }
  }

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
      options: { cutout: "70%", plugins: { legend: { display: false }, tooltip: { enabled: false } } }
    });
  } else {
    new Chart(investCtx, {
      type: "doughnut",
      data: {
        labels: ["Crypto", "Gold", "Land", "Business", "Stock", "Emergency Fund"], // 🟩 tambahkan label baru
        datasets: [{
          data,
          backgroundColor: [
            "#a5e262", // Crypto
            "#f1ca75ff", // Gold
            "#9e73f4", // Land
            "#f1905e", // Business
            "#44adf2", // Stock
            "#49a6e4ff"  // 🟩 Emergency Fund
          ],
          cutout: "70%"
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
// ================= LINE MONTHLY CHART =================
const lineCtx = document.getElementById("lineMonthlyChart");
if (lineCtx && window.MONTHLY_DATA) {
  const { labels, income, expense, investment } = window.MONTHLY_DATA;
  const ctx = lineCtx.getContext("2d");

  const makeGrad = (ctx, color) => {
    const g = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
    g.addColorStop(0, color.replace("1)", "0.2)"));
    g.addColorStop(1, color.replace("1)", "0)"));
    return g;
  };

  const colors = {
    income: "rgba(68,172,242,1)",    // biru pastel (Income)
    expense: "rgba(241,144,94,1)",   // oranye (Expense)
    invest: "rgba(165,226,96,1)"     // hijau muda (Investment)
  };

  new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Income",
          data: income,
          borderColor: colors.income,
          backgroundColor: makeGrad(ctx, colors.income),
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 2,
        },
        {
          label: "Expense",
          data: expense,
          borderColor: colors.expense,
          backgroundColor: makeGrad(ctx, colors.expense),
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 2,
        },
        {
          label: "Investment",
          data: investment,
          borderColor: colors.invest,
          backgroundColor: makeGrad(ctx, colors.invest),
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointRadius: 2,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: Rp ${ctx.parsed.y.toLocaleString("id-ID")}`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          ticks: { callback: (v) => v.toLocaleString("id-ID") },
          grid: { color: "rgba(0,0,0,0.06)" }
        },
        x: { grid: { display: false } }
      }
    }
  });
}

}); // END DOMContentLoaded
