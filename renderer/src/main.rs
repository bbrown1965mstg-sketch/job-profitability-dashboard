//! Native dashboard app — draws the Job Profitability Dashboard with
//! feetrender, either in a desktop window (default) or as a static PNG
//! (`--png [out]`). No web server, no browser.
//!
//! Reads sample_jobs.csv and derives the same columns ingest.py computes in
//! SQL: labor_cost = labor_hours * hourly_labor_rate,
//! net_profit = revenue - labor - materials - overhead,
//! profit_margin = 100 * net_profit / revenue.
//!
//! Cross-platform: fonts are picked from a fallback chain so the same binary
//! works on Linux (Liberation), macOS (Helvetica/Arial) and Windows (Segoe).

use feetrender::canvas::{Canvas, Font};
use feetrender::window;

// ---------------------------------------------------------------- palette
const BG: &str = "#0B0F17";
const CARD: &str = "#12161F";
const CARD_TOP: &str = "#171C26";
const BORDER: &str = "#232A36";
const GRID: &str = "#1B2130";
const AXIS: &str = "#2A3344";
const TEXT: &str = "#E6EDF3";
const DIM: &str = "#9BA6B4";
const FAINT: &str = "#55617A";
const REVENUE: &str = "#38BDF8";
const EXPENSES: &str = "#FB7185";
const PROFIT: &str = "#34D399";
const MARGIN: &str = "#A78BFA";
const LABOR: &str = "#F59E0B";
const LABOR_LINE: &str = "#FBBF24";

// Logical layout size; scaled to the physical canvas with letterboxing.
const LW: f64 = 1200.0;
const LH: f64 = 1360.0;
const W: f64 = LW; // layout shorthand used below
const MARGIN_X: f64 = 40.0;
const ALERT_PCT: f64 = 15.0;

const SANS_FAMILIES: &[&str] = &[
    "Liberation Sans", // Linux (Arial-metric clone)
    "Arial",           // macOS / Windows
    "Helvetica",       // macOS
    "Helvetica Neue",  // macOS
    "DejaVu Sans",     // other Linux distros
    "Segoe UI",        // Windows
];
const MONO_FAMILIES: &[&str] = &[
    "Liberation Mono",
    "Menlo",           // macOS
    "Courier New",     // macOS / Windows
    "DejaVu Sans Mono",
    "Consolas",        // Windows
];

// ------------------------------------------------------------------ data
struct Job {
    date: String,
    client: String,
    jtype: String,
    revenue: f64,
    labor_cost: f64,
    material: f64,
    overhead: f64,
}

impl Job {
    fn net(&self) -> f64 {
        self.revenue - self.labor_cost - self.material - self.overhead
    }
    fn margin(&self) -> f64 {
        if self.revenue == 0.0 { 0.0 } else { 100.0 * self.net() / self.revenue }
    }
}

fn find_csv() -> Result<String, String> {
    if let Some(arg) = std::env::args().nth(1) {
        if arg != "--png" {
            if std::path::Path::new(&arg).exists() {
                return Ok(arg);
            }
            return Err(format!("no such file: {arg}"));
        }
    }
    for cand in ["../sample_jobs.csv", "sample_jobs.csv"] {
        if std::path::Path::new(cand).exists() {
            return Ok(cand.to_string());
        }
    }
    Err("sample_jobs.csv not found (looked in . and ..) — pass a path as the first argument".into())
}

fn parse_csv(path: &str) -> Result<Vec<Job>, String> {
    let raw = std::fs::read_to_string(path).map_err(|e| format!("read {path}: {e}"))?;
    let mut jobs = Vec::new();
    for (i, line) in raw.lines().enumerate() {
        if line.trim().is_empty() || i == 0 {
            continue;
        }
        let f: Vec<&str> = line.split(',').map(str::trim).collect();
        if f.len() < 8 {
            return Err(format!("line {}: expected 8 fields, got {}", i + 1, f.len()));
        }
        let num = |j: usize| -> Result<f64, String> {
            f[j].parse::<f64>().map_err(|_| format!("line {}: bad number {:?}", i + 1, f[j]))
        };
        jobs.push(Job {
            date: f[0].to_string(),
            client: f[1].to_string(),
            jtype: f[2].to_string(),
            revenue: num(3)?,
            labor_cost: num(4)? * num(5)?, // labor_hours * hourly_labor_rate
            material: num(6)?,
            overhead: num(7)?,
        });
    }
    if jobs.is_empty() {
        return Err("no data rows found".into());
    }
    Ok(jobs)
}

// --------------------------------------------------------------- formatting
fn thousands(v: f64) -> String {
    let digits = format!("{:.0}", v);
    let n = digits.chars().count();
    let mut out = String::with_capacity(n + n / 3);
    for (i, ch) in digits.chars().enumerate() {
        out.push(ch);
        let rem = n - i - 1;
        if rem > 0 && rem % 3 == 0 {
            out.push(',');
        }
    }
    out
}

fn money(v: f64) -> String {
    let sign = if v < 0.0 { "-" } else { "" };
    format!("{sign}${}", thousands(v.abs()))
}

fn money_k(v: f64) -> String {
    let sign = if v < 0.0 { "-" } else { "" };
    let a = v.abs();
    if a >= 1000.0 {
        let k = a / 1000.0;
        let ks = if k >= 100.0 { format!("{k:.0}") } else { format!("{k:.1}") };
        format!("{sign}${ks}k")
    } else {
        format!("{sign}${a:.0}")
    }
}

fn pct(v: f64, nd: usize) -> String {
    format!("{:.*}%", nd, v)
}

fn month_label(ym: &str) -> String {
    const NAMES: [&str; 12] = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ];
    let parts: Vec<&str> = ym.split('-').collect();
    if parts.len() != 2 {
        return ym.to_string();
    }
    let m: usize = parts[1].parse().unwrap_or(1);
    let name = NAMES.get(m.saturating_sub(1)).copied().unwrap_or("?");
    format!("{name} {}", parts[0])
}

/// Round a max value up to a clean axis ceiling (1/2/5 × 10^k).
fn nice_ceiling(v: f64) -> f64 {
    if v <= 0.0 {
        return 1.0;
    }
    let exp = v.log10().floor() as i32;
    let base = 10f64.powi(exp);
    let scaled = v / base;
    let nice = if scaled <= 1.0 {
        1.0
    } else if scaled <= 2.0 {
        2.0
    } else if scaled <= 5.0 {
        5.0
    } else {
        10.0
    };
    nice * base
}

fn truncate(s: &str, max_chars: usize) -> String {
    if s.chars().count() <= max_chars {
        s.to_string()
    } else {
        let t: String = s.chars().take(max_chars - 1).collect();
        format!("{t}\u{2026}")
    }
}

// ------------------------------------------------------------ the dashboard
/// Everything derived from the data, computed once so the per-frame draw is
/// pure layout.
struct Dash {
    n_jobs: usize,
    n_types: usize,
    n_anomalies: usize,
    leak: f64,
    subtitle: String,
    total_revenue: f64,
    total_expense: f64,
    net_profit: f64,
    overall_margin: f64,
    /// (type name, jobs, revenue, expenses, net) sorted by net desc
    by_type: Vec<(String, usize, f64, f64, f64)>,
    /// (month label, revenue, labor cost, labor % of revenue)
    monthly: Vec<(String, f64, f64, f64)>,
    /// (rank, client, jobs, revenue str, net str, margin str, negative?, low margin?)
    clients_top: Vec<ClientRow>,
    clients_bottom: Vec<ClientRow>,
    sans: String,
    mono: String,
}

#[derive(Clone)]
struct ClientRow {
    name: String,
    jobs: usize,
    net_val: f64,
    rev: String,
    net: String,
    margin: String,
    neg: bool,
    low_margin: bool,
}

fn pick_family(candidates: &[&str]) -> Option<String> {
    for family in candidates {
        if Font::new(family, 12, "normal", "roman").is_ok() {
            return Some(family.to_string());
        }
    }
    None
}

impl Dash {
    fn build(jobs: &[Job]) -> Result<Dash, feetrender::Error> {
        let sans = pick_family(SANS_FAMILIES)
            .ok_or_else(|| feetrender::Error::FontError("no sans-serif font found".into()))?;
        let mono = pick_family(MONO_FAMILIES).unwrap_or_else(|| sans.clone());

        let total_revenue: f64 = jobs.iter().map(|j| j.revenue).sum();
        let total_expense: f64 = jobs.iter().map(|j| j.labor_cost + j.material + j.overhead).sum();
        let net_profit: f64 = jobs.iter().map(|j| j.net()).sum();
        let overall_margin = if total_revenue > 0.0 { 100.0 * net_profit / total_revenue } else { 0.0 };

        let anomalies: Vec<&Job> = jobs.iter().filter(|j| j.margin() < ALERT_PCT).collect();
        let leak: f64 = anomalies.iter().map(|j| j.net()).sum();

        let mut types: Vec<String> = jobs.iter().map(|j| j.jtype.clone()).collect();
        types.sort();
        types.dedup();
        let mut by_type: Vec<(String, usize, f64, f64, f64)> = vec![];
        for t in &types {
            let rows: Vec<&Job> = jobs.iter().filter(|j| &j.jtype == t).collect();
            let rev: f64 = rows.iter().map(|j| j.revenue).sum();
            let exp: f64 = rows.iter().map(|j| j.labor_cost + j.material + j.overhead).sum();
            let net: f64 = rows.iter().map(|j| j.net()).sum();
            by_type.push((t.clone(), rows.len(), rev, exp, net));
        }
        by_type.sort_by(|a, b| b.4.partial_cmp(&a.4).unwrap());

        let mut months: Vec<String> = jobs.iter().map(|j| j.date[..7].to_string()).collect();
        months.sort();
        months.dedup();
        let monthly: Vec<(String, f64, f64, f64)> = months
            .iter()
            .map(|m| {
                let rows: Vec<&Job> = jobs.iter().filter(|j| &j.date[..7] == m).collect();
                let rev: f64 = rows.iter().map(|j| j.revenue).sum();
                let labor: f64 = rows.iter().map(|j| j.labor_cost).sum();
                let lp = if rev > 0.0 { 100.0 * labor / rev } else { 0.0 };
                (month_label(m), rev, labor, lp)
            })
            .collect();

        let mut names: Vec<String> = jobs.iter().map(|j| j.client.clone()).collect();
        names.sort();
        names.dedup();
        let mut clients: Vec<ClientRow> = vec![];
        for n in &names {
            let rows: Vec<&Job> = jobs.iter().filter(|j| &j.client == n).collect();
            let rev: f64 = rows.iter().map(|j| j.revenue).sum();
            let net: f64 = rows.iter().map(|j| j.net()).sum();
            let margin = if rev > 0.0 { 100.0 * net / rev } else { 0.0 };
            clients.push(ClientRow {
                name: n.clone(),
                jobs: rows.len(),
                net_val: net,
                rev: money_k(rev),
                net: money_k(net),
                margin: pct(margin, 1),
                neg: net < 0.0,
                low_margin: margin < ALERT_PCT,
            });
        }
        let mut by_net = clients.clone();
        by_net.sort_by(|a, b| b.net_val.partial_cmp(&a.net_val).unwrap());
        let clients_top: Vec<ClientRow> = by_net.into_iter().take(5).collect();
        let mut by_net_asc = clients;
        by_net_asc.sort_by(|a, b| a.net_val.partial_cmp(&b.net_val).unwrap());
        let clients_bottom: Vec<ClientRow> = by_net_asc.into_iter().take(5).collect();

        let date_min = jobs.iter().map(|j| j.date.as_str()).min().unwrap_or("");
        let date_max = jobs.iter().map(|j| j.date.as_str()).max().unwrap_or("");
        let subtitle = format!(
            "{} jobs \u{2022} {} \u{2013} {} \u{2022} {} job types \u{2022} {} months \u{2022} native window, no server",
            jobs.len(),
            &date_min[5..].replace('-', "/"),
            format!("{}/{}", &date_max[5..7], &date_max[8..]),
            types.len(),
            months.len(),
        );

        Ok(Dash {
            n_jobs: jobs.len(),
            n_types: types.len(),
            n_anomalies: anomalies.len(),
            leak,
            subtitle,
            total_revenue,
            total_expense,
            net_profit,
            overall_margin,
            by_type,
            monthly,
            clients_top,
            clients_bottom,
            sans,
            mono,
        })
    }

    fn draw(&self, c: &mut Canvas) {
        let empty: Vec<String> = vec![];
        let cw = c.winfo_width() as f64;
        let ch = c.winfo_height() as f64;
        // Letterbox the 1200×1360 logical layout into the physical canvas.
        let k = (cw / LW).min(ch / LH);
        let ox = (cw - LW * k) / 2.0;
        let oy = (ch - LH * k) / 2.0;
        let px = |x: f64| ox + x * k;
        let py = |y: f64| oy + y * k;
        let d = |v: f64| v * k; // scale a distance
        let lw = |v: f64| ((v * k).ceil() as i64).max(1); // scale a line width
        let sans = |size: i64, bold: bool| {
            Font::new(
                &self.sans,
                ((size as f64) * k).round().max(1.0) as i64,
                if bold { "bold" } else { "normal" },
                "roman",
            )
        };
        let mono = |size: i64| {
            Font::new(&self.mono, ((size as f64) * k).round().max(1.0) as i64, "normal", "roman")
        };

        // The canvas is retained-mode: clear it, paint the backdrop, redraw.
        c.delete("all");
        c.create_rectangle(0.0, 0.0, cw, ch, Some(BG), None, None, false, &empty);

        // ---- header ---------------------------------------------------------
        c.create_rectangle(px(MARGIN_X), py(18.0), px(MARGIN_X + 44.0), py(62.0),
                           Some("#34D399"), None, None, false, &empty);
        c.create_text(px(MARGIN_X + 22.0), py(46.0), "P", sans(24, true).unwrap(),
                      Some("#07121B"), "center", &empty);
        c.create_text(px(MARGIN_X + 60.0), py(22.0), "Job Profitability Dashboard",
                      sans(32, true).unwrap(), Some(TEXT), "nw", &empty);
        c.create_text(px(MARGIN_X + 60.0), py(60.0), &self.subtitle,
                      sans(11, false).unwrap(), Some(DIM), "nw", &empty);
        let badge = "RENDERED WITH FEETRENDER";
        let mut mb = sans(11, false).unwrap();
        let bw = mb.measure(badge);
        c.create_rectangle(px(W) - d(MARGIN_X + bw + 20.0), py(24.0), px(W) - d(MARGIN_X), py(48.0),
                           Some(CARD), Some(BORDER), Some(lw(1.0)), false, &empty);
        c.create_text(px(W) - d(MARGIN_X + bw + 10.0), py(35.0), badge,
                      sans(11, false).unwrap(), Some(DIM), "nw", &empty);
        c.create_line(vec![px(MARGIN_X), py(84.0), px(W - MARGIN_X), py(84.0)],
                      Some(BORDER), Some(lw(1.0)), &empty);

        // ---- anomaly banner -------------------------------------------------
        let (banner_bg, banner_edge, banner_accent, l1, l1_col, l2) = if self.n_anomalies > 0 {
            (
                "#1B1119", "#5C2A38", EXPENSES,
                format!("ANOMALY ALERT \u{2014} {} job(s) below {:.0}% profit margin",
                        self.n_anomalies, ALERT_PCT),
                EXPENSES,
                format!("net result of these jobs: {} \u{2014} review pricing, labor or material costs",
                        money(self.leak)),
            )
        } else {
            (
                "#0F1A16", "#2A4A3A", PROFIT,
                format!("ALL CLEAR \u{2014} every job is at or above the {:.0}% margin floor", ALERT_PCT),
                PROFIT,
                String::new(),
            )
        };
        let y = 102.0;
        let banner_h = 44.0;
        c.create_rectangle(px(MARGIN_X), py(y), px(W - MARGIN_X), py(y + banner_h),
                           Some(banner_bg), Some(banner_edge), Some(lw(1.0)), false, &empty);
        c.create_rectangle(px(MARGIN_X), py(y), px(MARGIN_X + 4.0), py(y + banner_h),
                           Some(banner_accent), None, None, false, &empty);
        c.create_text(px(MARGIN_X + 20.0), py(y + 13.0), &l1, sans(12, true).unwrap(),
                      Some(l1_col), "nw", &empty);
        if !l2.is_empty() {
            c.create_text(px(MARGIN_X + 20.0), py(y + 30.0), &l2, sans(11, false).unwrap(),
                          Some(DIM), "nw", &empty);
        }

        // ---- KPI cards --------------------------------------------------------
        let y = y + banner_h + 24.0; // 170
        let card_h = 108.0;
        let gap = 16.0;
        let content_w = LW - 2.0 * MARGIN_X;
        let card_w = (content_w - 3.0 * gap) / 4.0;
        let kpis: [(&str, &str, String, String); 4] = [
            ("TOTAL REVENUE", REVENUE, money(self.total_revenue),
             format!("{} jobs", self.n_jobs)),
            ("TOTAL EXPENSES", EXPENSES, money(self.total_expense),
             format!("{:.0}% of revenue", 100.0 * self.total_expense / self.total_revenue)),
            ("NET PROFIT", PROFIT, money(self.net_profit),
             format!("{} avg margin", pct(self.overall_margin, 1))),
            ("OVERALL MARGIN", MARGIN, pct(self.overall_margin, 1),
             format!("{} anomaly jobs", self.n_anomalies)),
        ];
        for (i, (label, accent, value, sub)) in kpis.iter().enumerate() {
            let x = MARGIN_X + i as f64 * (card_w + gap);
            c.create_rectangle(px(x), py(y), px(x + card_w), py(y + card_h),
                               Some(CARD_TOP), Some(BORDER), Some(lw(1.0)), false, &empty);
            c.create_rectangle(px(x), py(y), px(x + 4.0), py(y + card_h),
                               Some(accent), None, None, false, &empty);
            c.create_text(px(x + 20.0), py(y + 16.0), label, sans(12, true).unwrap(),
                          Some(DIM), "nw", &empty);
            c.create_text(px(x + 20.0), py(y + 38.0), value, sans(28, true).unwrap(),
                          Some(TEXT), "nw", &empty);
            c.create_text(px(x + 20.0), py(y + 80.0), sub, sans(11, false).unwrap(),
                          Some(FAINT), "nw", &empty);
        }

        // ---- section title helper -------------------------------------------
        let mut y = y + card_h + 30.0; // 308
        let section = |c: &mut Canvas, y: &mut f64, num: &str, title: &str| {
            *y += 4.0;
            c.create_rectangle(px(MARGIN_X), py(*y), px(MARGIN_X + 30.0), py(*y + 24.0),
                               Some("#34D399"), None, None, false, &empty);
            c.create_text(px(MARGIN_X + 15.0), py(*y + 13.0), num, sans(13, true).unwrap(),
                          Some("#07121B"), "center", &empty);
            c.create_text(px(MARGIN_X + 42.0), py(*y + 1.0), title, sans(19, true).unwrap(),
                          Some(TEXT), "nw", &empty);
            *y += 34.0;
        };

        section(c, &mut y, "01", "Profitability by Job Type");

        // legend
        let legend: [(&str, &str); 3] = [("Revenue", REVENUE), ("Expenses", EXPENSES), ("Net Profit", PROFIT)];
        let mut lx = W - MARGIN_X;
        for (name, col) in legend.iter().rev() {
            let mut m = sans(11, false).unwrap();
            let w = m.measure(name);
            c.create_text(px(lx), py(y - 6.0), name, sans(11, false).unwrap(), Some(DIM), "ne", &empty);
            lx -= w + 6.0;
            c.create_rectangle(px(lx - 10.0), py(y - 15.0), px(lx), py(y - 5.0),
                               Some(col), None, None, false, &empty);
            lx -= 22.0;
        }

        let plot_l = MARGIN_X + 46.0;
        let plot_r = W - MARGIN_X;
        let plot_t = y + 6.0;
        let plot_b = plot_t + 258.0;
        let max_val = self.by_type.iter().map(|t| t.2.max(t.3.max(t.4))).fold(0.0_f64, f64::max);
        let ceil = nice_ceiling(max_val * 1.08);

        for i in 0..=4 {
            let gy = plot_b - (plot_b - plot_t) * i as f64 / 4.0;
            c.create_line(vec![px(plot_l), py(gy), px(plot_r), py(gy)], Some(GRID), Some(lw(1.0)), &empty);
            let lbl = format!("${:.0}k", ceil * i as f64 / 4000.0);
            c.create_text(px(plot_l - 8.0), py(gy), &lbl, sans(11, false).unwrap(), Some(FAINT), "e", &empty);
        }
        c.create_line(vec![px(plot_l), py(plot_b), px(plot_r), py(plot_b)], Some(AXIS), Some(lw(1.0)), &empty);

        let n = self.by_type.len() as f64;
        let group_w = (plot_r - plot_l) / n;
        let bar_w = ((group_w - 36.0) / 3.0).min(30.0);
        for (i, (name, jobs_n, rev, exp, net)) in self.by_type.iter().enumerate() {
            let gx = plot_l + i as f64 * group_w;
            let group_cx = gx + group_w / 2.0;
            let bars = [(*rev, REVENUE), (*exp, EXPENSES), (*net, PROFIT)];
            let start = group_cx - (3.0 * bar_w + 2.0 * 6.0) / 2.0;
            for (b, (val, col)) in bars.iter().enumerate() {
                let bx = start + b as f64 * (bar_w + 6.0);
                let h = ((val / ceil) * (plot_b - plot_t)).abs();
                let (top, bottom) = if *val >= 0.0 { (plot_b - h, plot_b) } else { (plot_b, plot_b + h) };
                c.create_rectangle(px(bx), py(top), px(bx + bar_w), py(bottom),
                                   Some(col), None, None, false, &empty);
                let lbl = money_k(*val);
                c.create_text(px(bx + bar_w / 2.0), py(top) - d(16.0), &lbl,
                              mono(10).unwrap(), Some(DIM), "center", &empty);
            }
            c.create_text(px(group_cx), py(plot_b + 14.0), name, sans(13, false).unwrap(),
                          Some(TEXT), "n", &empty);
            c.create_text(px(group_cx), py(plot_b + 32.0), &format!("{} jobs", jobs_n),
                          sans(11, false).unwrap(), Some(FAINT), "n", &empty);
        }
        let mut y = plot_b + 56.0;

        // ---- section 02 ------------------------------------------------------
        y += 14.0;
        section(c, &mut y, "02", "Labor Cost vs. Revenue by Month");

        let legend2: [(&str, &str); 3] =
            [("Revenue", REVENUE), ("Labor Cost", LABOR), ("Labor % of Revenue", LABOR_LINE)];
        let mut lx = W - MARGIN_X;
        for (name, col) in legend2.iter().rev() {
            let mut m = sans(11, false).unwrap();
            let w = m.measure(name);
            c.create_text(px(lx), py(y - 6.0), name, sans(11, false).unwrap(), Some(DIM), "ne", &empty);
            lx -= w + 6.0;
            if *col == LABOR_LINE {
                c.create_line(vec![px(lx - 14.0), py(y - 10.0), px(lx), py(y - 10.0)],
                              Some(LABOR_LINE), Some(lw(3.0)), &empty);
                c.create_oval(px(lx - 8.0), py(y - 14.0), px(lx - 0.5), py(y - 6.0),
                              Some(LABOR_LINE), Some(BG), Some(lw(1.0)), &empty);
            } else {
                c.create_rectangle(px(lx - 10.0), py(y - 15.0), px(lx), py(y - 5.0),
                                   Some(col), None, None, false, &empty);
            }
            lx -= 22.0;
        }

        let plot_t = y + 6.0;
        let plot_b = plot_t + 210.0;
        let max_rev = self.monthly.iter().map(|m| m.1).fold(0.0_f64, f64::max);
        let ceil = nice_ceiling(max_rev * 1.08);
        for i in 0..=4 {
            let gy = plot_b - (plot_b - plot_t) * i as f64 / 4.0;
            c.create_line(vec![px(plot_l), py(gy), px(plot_r), py(gy)], Some(GRID), Some(lw(1.0)), &empty);
            let lbl = format!("${:.0}k", ceil * i as f64 / 4000.0);
            c.create_text(px(plot_l - 8.0), py(gy), &lbl, sans(11, false).unwrap(), Some(FAINT), "e", &empty);
        }
        c.create_line(vec![px(plot_l), py(plot_b), px(plot_r), py(plot_b)], Some(AXIS), Some(lw(1.0)), &empty);

        let n = self.monthly.len() as f64;
        let group_w = (plot_r - plot_l) / n;
        let bar_w = ((group_w - 44.0) / 2.0).min(38.0);
        let max_pct = self.monthly.iter().map(|m| m.3).fold(0.0_f64, f64::max);
        let pct_ceil = nice_ceiling(max_pct * 1.25).max(10.0);
        let mut line_pts: Vec<f64> = vec![];
        let mut line_labels: Vec<(f64, f64, String)> = vec![];
        for (i, (label, rev, labor, lp)) in self.monthly.iter().enumerate() {
            let gx = plot_l + i as f64 * group_w;
            let group_cx = gx + group_w / 2.0;
            for (j, (v, col)) in [(*rev, REVENUE), (*labor, LABOR)].iter().enumerate() {
                let bx = group_cx - bar_w - 4.0 + j as f64 * (bar_w + 8.0);
                let h = (v / ceil) * (plot_b - plot_t);
                c.create_rectangle(px(bx), py(plot_b - h), px(bx + bar_w), py(plot_b),
                                   Some(col), None, None, false, &empty);
            }
            let ly = plot_b - (lp / pct_ceil) * (plot_b - plot_t);
            line_pts.extend_from_slice(&[px(group_cx), py(ly)]);
            line_labels.push((px(group_cx), py(ly), pct(*lp, 1)));
            c.create_text(px(group_cx), py(plot_b + 14.0), label, sans(13, false).unwrap(),
                          Some(TEXT), "n", &empty);
        }
        for i in 0..=4 {
            let gy = plot_b - (plot_b - plot_t) * i as f64 / 4.0;
            let lbl = format!("{:.0}%", pct_ceil * i as f64 / 4.0);
            c.create_text(px(plot_r) + d(8.0), py(gy), &lbl, sans(11, false).unwrap(),
                          Some(FAINT), "nw", &empty);
        }
        if line_pts.len() >= 4 {
            c.create_line(line_pts.clone(), Some(LABOR_LINE), Some(lw(3.0)), &empty);
        }
        for (mx, my, lbl) in &line_labels {
            c.create_oval(mx - d(5.0), my - d(5.0), mx + d(5.0), my + d(5.0),
                          Some(LABOR_LINE), Some(BG), Some(lw(2.0)), &empty);
            c.create_text(*mx, my - d(20.0), lbl, mono(10).unwrap(), Some(LABOR_LINE),
                          "center", &empty);
        }
        let mut y = plot_b + 40.0;

        // ---- section 03 ------------------------------------------------------
        y += 20.0;
        section(c, &mut y, "03", "Client Profitability \u{2014} Top & Bottom 5");

        let content_w = LW - 2.0 * MARGIN_X;
        let col_w = (content_w - 24.0) / 2.0;
        let row_h = 27.0;
        let table_top = y + 6.0;
        for (side, (title, title_col, rows)) in [
            (0.0, ("TOP 5 MOST PROFITABLE", PROFIT, &self.clients_top)),
            (col_w + 24.0, ("BOTTOM 5 LEAST PROFITABLE", EXPENSES, &self.clients_bottom)),
        ] {
            let x0 = MARGIN_X + side;
            let x1 = x0 + col_w;
            let hy = table_top + 38.0;
            c.create_rectangle(px(x0), py(table_top), px(x1), py(hy + 26.0 + 5.0 * row_h + 8.0),
                               Some(CARD), Some(BORDER), Some(lw(1.0)), false, &empty);
            c.create_text(px(x0 + 14.0), py(table_top + 11.0), title, sans(12, true).unwrap(),
                          Some(title_col), "nw", &empty);
            c.create_text(px(x0 + 14.0), py(hy), "CLIENT", sans(11, false).unwrap(),
                          Some(FAINT), "nw", &empty);
            c.create_text(px(x0 + col_w - 14.0 - 3.0 * 62.0 - 8.0), py(hy), "JOBS",
                          sans(11, false).unwrap(), Some(FAINT), "nw", &empty);
            c.create_text(px(x1 - 14.0 - 2.0 * 62.0), py(hy), "REVENUE", sans(11, false).unwrap(),
                          Some(FAINT), "ne", &empty);
            c.create_text(px(x1 - 14.0 - 62.0), py(hy), "NET", sans(11, false).unwrap(),
                          Some(FAINT), "ne", &empty);
            c.create_text(px(x1 - 14.0), py(hy), "MARGIN", sans(11, false).unwrap(),
                          Some(FAINT), "ne", &empty);
            c.create_line(vec![px(x0 + 12.0), py(hy + 16.0), px(x1 - 12.0), py(hy + 16.0)],
                          Some(GRID), Some(lw(1.0)), &empty);
            for (r, row) in rows.iter().enumerate() {
                let ry = hy + 26.0 + r as f64 * row_h;
                let name_col = if row.neg { EXPENSES } else { TEXT };
                c.create_text(px(x0 + 14.0), py(ry), &format!("{}. {}", r + 1, truncate(&row.name, 26)),
                              sans(13, false).unwrap(), Some(name_col), "nw", &empty);
                c.create_text(px(x0 + col_w - 14.0 - 3.0 * 62.0), py(ry), &format!("{}  ", row.jobs),
                              mono(13).unwrap(), Some(DIM), "ne", &empty);
                c.create_text(px(x1 - 14.0 - 2.0 * 62.0 - 8.0), py(ry), &row.rev,
                              mono(13).unwrap(), Some(DIM), "ne", &empty);
                c.create_text(px(x1 - 14.0 - 62.0 - 8.0), py(ry), &row.net,
                              mono(13).unwrap(), Some(if row.neg { EXPENSES } else { PROFIT }), "ne", &empty);
                c.create_text(px(x1 - 14.0), py(ry), &row.margin,
                              mono(13).unwrap(), Some(if row.low_margin { EXPENSES } else { DIM }), "ne", &empty);
                if r < 4 {
                    let sy = ry + row_h - 7.0;
                    c.create_line(vec![px(x0 + 12.0), py(sy), px(x1 - 12.0), py(sy)],
                                  Some(GRID), Some(lw(1.0)), &empty);
                }
            }
        }
        let y = table_top + 38.0 + 26.0 + 5.0 * row_h + 8.0;

        // ---- footer ----------------------------------------------------------
        let y = y + 26.0;
        c.create_line(vec![px(MARGIN_X), py(y), px(W - MARGIN_X), py(y)], Some(BORDER), Some(lw(1.0)), &empty);
        c.create_text(px(W / 2.0), py(y + 20.0),
                      "margins derived live: labor = hours \u{d7} rate \u{2022} net = revenue \u{2212} labor \u{2212} materials \u{2212} overhead",
                      sans(11, false).unwrap(), Some(FAINT), "n", &empty);
        c.create_text(px(W / 2.0), py(y + 40.0), "rendered with feetrender",
                      sans(11, false).unwrap(), Some(FAINT), "n", &empty);
    }
}

// ------------------------------------------------------------------- main
fn main() {
    let args: Vec<String> = std::env::args().collect();
    let png_mode = args.iter().any(|a| a == "--png");
    let png_out = args
        .iter()
        .position(|a| a == "--png")
        .and_then(|i| args.get(i + 1).cloned());

    let csv = match find_csv() {
        Ok(p) => p,
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    };
    let jobs = match parse_csv(&csv) {
        Ok(j) => j,
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    };
    let dash = match Dash::build(&jobs) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("error: {e}");
            std::process::exit(1);
        }
    };
    eprintln!(
        "fonts: sans={} mono={} ({} jobs, {} anomalies)",
        dash.sans, dash.mono, dash.n_jobs, dash.n_anomalies
    );

    if png_mode {
        // 2× device scale for a crisp README snapshot.
        let mut canvas = Canvas::new(LW as i64, LH as i64, BG, 2.0).expect("canvas");
        dash.draw(&mut canvas);
        canvas.render();
        let out = png_out.as_deref().unwrap_or("dashboard.png");
        canvas.save_png(out).expect("save png");
        eprintln!("wrote {out}");
        return;
    }

    // Native window. The scene is static, so redraw only when the compositor
    // asks and throttle the busy redraw loop feetrender's demo path runs at.
    let drawn = std::sync::atomic::AtomicU64::new(0);
    let frame = move |c: &mut Canvas, _t: f64| {
        dash.draw(c);
        drawn.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        std::thread::sleep(std::time::Duration::from_millis(14));
    };
    if let Err(e) = window::run("Job Profitability Dashboard", 1200, 1360, frame, |_| {}) {
        eprintln!("error: {e}");
        std::process::exit(1);
    }
}
