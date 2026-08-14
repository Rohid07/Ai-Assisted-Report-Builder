frappe.pages["ai-report-view"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Report"),
		single_column: true,
	});
	new AIReportView(page);
};

class AIReportView {
	constructor(page) {
		this.page = page;
		this.name = this.resolve_name();
		this.body = $('<div class="ai-report"></div>').appendTo(this.page.main);
		this.inject_styles();

		this.page.set_primary_action(__("Refresh"), () => this.name ? this.load() : this.show_picker(), "refresh");
		this.page.add_menu_item(__("Export Excel"), () => this.export("Excel"));
		this.page.add_menu_item(__("Export CSV"), () => this.export("CSV"));
		this.page.add_menu_item(__("Print"), () => window.print());

		if (this.name) this.load();
		else this.show_picker();
	}

	resolve_name() {
		// Accept ?name=, route_options.name, or a trailing path segment.
		const qs = new URLSearchParams(location.search).get("name");
		if (qs) return qs;
		if (frappe.route_options && frappe.route_options.name) {
			const n = frappe.route_options.name;
			delete frappe.route_options.name;
			return n;
		}
		const route = frappe.get_route ? frappe.get_route() : [];
		if (route && route.length > 1) return route[route.length - 1];
		return null;
	}

	show_picker() {
		this.page.set_title(__("AI Reports"));
		this.body.html(`<div class="text-muted">${__("Loading your reports…")}</div>`);
		frappe.call({
			method: "ai_report_builder.ai.report_view.list_ai_reports",
			callback: (r) => {
				const items = r.message || [];
				if (!items.length) {
					this.body.html(`<div class="text-muted">${__("No saved reports yet. Ask a question in the AI Assistant and click ‘Save as Report’.")}</div>`);
					return;
				}
				const rows = items.map((it) => `
					<div class="ai-r-pick" data-name="${frappe.utils.escape_html(it.name)}">
						<span class="ai-r-pick-title">${frappe.utils.escape_html(it.report_title || it.name)}</span>
						<span class="text-muted small">${frappe.utils.escape_html(it.reference_doctype || "")} · ${frappe.utils.escape_html(it.report_kind || "")}</span>
					</div>`).join("");
				this.body.html(`<h3>${__("Your saved reports")}</h3><div class="ai-r-picklist">${rows}</div>`);
				this.body.find(".ai-r-pick").on("click", (e) => {
					const nm = $(e.currentTarget).data("name");
					this.name = nm;
					this.load();
				});
			},
			error: () => this.body.html(`<div class="ai-r-error">${__("Could not load your reports.")}</div>`),
		});
	}

	load() {
		this.body.html(`<div class="text-muted">${__("Loading…")}</div>`);
		frappe.call({
			method: "ai_report_builder.ai.report_view.run_ai_report",
			args: { name: this.name },
			callback: (r) => this.render(r.message || {}),
			error: () => this.body.html(`<div class="ai-r-error">${__("Could not load this report.")}</div>`),
		});
	}

	render(data) {
		this.data = data;
		if (data.error) {
			this.body.html(`<div class="ai-r-error">${__("This report could not be run: {0}", [data.error])}</div>`);
			return;
		}
		this.page.set_title(data.title || __("AI Report"));
		this.body.empty();

		$(`
			<div class="ai-r-head">
				<h2 class="ai-r-title">${frappe.utils.escape_html(data.title || "")}</h2>
				${data.description ? `<div class="text-muted ai-r-desc">${frappe.utils.escape_html(data.description)}</div>` : ""}
				<div class="text-muted small ai-r-meta">
					${frappe.utils.escape_html(data.reference_doctype || "")} · ${data.count} ${__("rows")}
				</div>
			</div>
		`).appendTo(this.body);

		// Conversational refinement bar.
		const $refine = $(`
			<div class="ai-r-refine">
				<input type="text" class="form-control ai-r-refine-input"
					placeholder="${__("Refine this report… e.g. “add a due date column”, “only this month”, “sort by amount”")}">
				<button class="btn btn-default btn-sm ai-r-refine-btn">${__("Refine")}</button>
			</div>
		`).appendTo(this.body);
		this.$refine = $refine.find(".ai-r-refine-input");
		$refine.find(".ai-r-refine-btn").on("click", () => this.refine());
		this.$refine.on("keydown", (e) => {
			if (e.key === "Enter") {
				e.preventDefault();
				this.refine();
			}
		});

		if (data.chart) this.render_chart(data.chart);
		this.render_table(data);
	}

	refine() {
		const instruction = (this.$refine.val() || "").trim();
		if (!instruction) return;
		frappe.dom.freeze(__("Refining report…"));
		frappe.call({
			method: "ai_report_builder.ai.report_view.refine_report",
			args: { name: this.name, instruction },
			callback: (r) => {
				frappe.dom.unfreeze();
				const m = r.message || {};
				if (m.error) {
					frappe.show_alert({ message: __("Couldn’t apply that change — try rephrasing."), indicator: "red" });
					return;
				}
				this.render(m);
				frappe.show_alert({ message: __("Report updated."), indicator: "green" });
			},
			error: () => frappe.dom.unfreeze(),
		});
	}

	render_chart(chart) {
		const $wrap = $('<div class="ai-r-chart"></div>').appendTo(this.body);
		try {
			new frappe.Chart($wrap[0], {
				data: { labels: chart.labels, datasets: [{ name: chart.title, values: chart.values }] },
				type: "bar",
				height: 260,
				colors: ["#4f8bf0"],
			});
		} catch (e) {
			$wrap.remove();
		}
	}

	render_table(data) {
		const cols = data.columns || [];
		const numeric = (ft) => ["Currency", "Float", "Int", "Percent"].includes(ft);
		const fmt = (val, col) => {
			if (val === null || val === undefined || val === "") return "";
			try {
				return frappe.format(val, { fieldtype: col.fieldtype }, { inline: true });
			} catch (e) {
				return frappe.utils.escape_html(String(val));
			}
		};

		const head = cols.map((c) => `<th class="${numeric(c.fieldtype) ? "text-right" : ""}">${frappe.utils.escape_html(c.label)}</th>`).join("");
		const body = (data.rows || []).map((row) => {
			const tds = cols.map((c) => `<td class="${numeric(c.fieldtype) ? "text-right" : ""}">${fmt(row[c.field], c)}</td>`).join("");
			return `<tr>${tds}</tr>`;
		}).join("");

		let foot = "";
		if (data.totals && Object.keys(data.totals).length) {
			const tds = cols.map((c, i) => {
				if (i === 0) return `<td><strong>${__("Total")}</strong></td>`;
				if (c.field in data.totals) return `<td class="text-right"><strong>${fmt(data.totals[c.field], c)}</strong></td>`;
				return "<td></td>";
			}).join("");
			foot = `<tfoot><tr>${tds}</tr></tfoot>`;
		}

		$(`
			<div class="ai-r-table-wrap">
				<table class="table table-bordered ai-r-table">
					<thead><tr>${head}</tr></thead>
					<tbody>${body || `<tr><td colspan="${cols.length || 1}" class="text-muted">${__("No data.")}</td></tr>`}</tbody>
					${foot}
				</table>
			</div>
		`).appendTo(this.body);
	}

	export(file_format) {
		if (!this.name) return;
		// Server-side download (Excel via xlsx, CSV via csvutils) — formatted and
		// consistent with the on-screen columns/totals.
		open_url_post(
			"/api/method/ai_report_builder.ai.report_view.export_ai_report",
			{ name: this.name, file_format }
		);
	}

	inject_styles() {
		if (document.getElementById("ai-report-view-styles")) return;
		$(`<style id="ai-report-view-styles">
			.ai-report { max-width: 960px; margin: 0 auto; }
			.ai-r-head { margin-bottom: 16px; }
			.ai-r-title { margin: 0 0 4px; }
			.ai-r-desc { margin-bottom: 4px; }
			.ai-r-chart { margin: 8px 0 20px; }
			.ai-r-table-wrap { overflow-x: auto; }
			.ai-r-table { font-size: 13px; }
			.ai-r-table tfoot td { background: var(--bg-light-gray, #f4f5f6); }
			.ai-r-error { color: var(--red-600, #c0392b); padding: 12px 0; }
			.text-right { text-align: right; }
			.ai-r-pick { display: flex; justify-content: space-between; align-items: center;
				padding: 10px 12px; border: 1px solid var(--border-color, #e0e0e0);
				border-radius: 8px; margin: 6px 0; cursor: pointer; }
			.ai-r-pick:hover { background: var(--bg-light-gray, #f4f5f6); }
			.ai-r-pick-title { font-weight: 500; }
			.ai-r-refine { display: flex; gap: 8px; margin: 4px 0 16px; }
			.ai-r-refine-input { flex: 1; }
		</style>`).appendTo(document.head);
	}
}
