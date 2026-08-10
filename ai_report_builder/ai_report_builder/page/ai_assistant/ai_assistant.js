frappe.pages["ai-assistant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Assistant"),
		single_column: true,
	});

	page.add_inner_button(__("Settings"), () => {
		frappe.set_route("Form", "AI Assistant Settings", "AI Assistant Settings");
	});

	new AIAssistant(page);
};

class AIAssistant {
	constructor(page) {
		this.page = page;
		this.render();
	}

	render() {
		this.wrapper = $(`
			<div class="ai-assistant">
				<div class="ai-chat-log" data-log></div>
				<div class="ai-input-row">
					<textarea class="form-control ai-input" rows="1"
						placeholder="${__("Ask a business question, e.g. “how many customers are in the Commercial group?”")}"></textarea>
					<button class="btn btn-primary ai-send">${__("Ask")}</button>
				</div>
				<div class="ai-hint text-muted small">
					${__("Read-only. Queries respect your ERPNext permissions.")}
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$log = this.wrapper.find("[data-log]");
		this.$input = this.wrapper.find(".ai-input");
		this.$send = this.wrapper.find(".ai-send");

		this.inject_styles();

		this.$send.on("click", () => this.ask());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.ask();
			}
		});
	}

	ask() {
		const question = (this.$input.val() || "").trim();
		if (!question) return;
		this.$input.val("");
		this.add_message("user", frappe.utils.escape_html(question));

		const $thinking = this.add_message("assistant", `<span class="text-muted">${__("Thinking…")}</span>`);
		this.$send.prop("disabled", true);

		frappe.call({
			method: "ai_report_builder.api.ask",
			args: { question },
			callback: (r) => {
				$thinking.remove();
				if (r.message) this.render_answer(r.message);
			},
			error: () => {
				$thinking.remove();
				this.add_message(
					"assistant",
					`<div class="ai-error">${__("Something went wrong. Check AI Assistant Settings (API key / provider).")}</div>`
				);
			},
			always: () => this.$send.prop("disabled", false),
		});
	}

	render_answer(msg) {
		const parts = [];

		if (msg.error) {
			const label =
				msg.error === "permission_denied"
					? __("You don’t have permission to read that data.")
					: __("This query couldn’t be run.");
			parts.push(`<div class="ai-error">${label}</div>`);
		}

		if (msg.answer) {
			parts.push(`<div class="ai-text">${frappe.utils.escape_html(msg.answer).replace(/\n/g, "<br>")}</div>`);
		}

		if (msg.rows && msg.rows.length) {
			parts.push(this.render_table(msg.columns, msg.rows));
		} else if (!msg.error && !msg.answer) {
			parts.push(`<div class="text-muted">${__("No results.")}</div>`);
		}

		if (msg.row_truncated || msg.col_truncated) {
			parts.push(
				`<div class="text-muted small">${__("Results were truncated for display.")}</div>`
			);
		}

		const $m = this.add_message("assistant", parts.join(""));

		// §4.8 — Save as Report only when the query is savable (no group_by).
		if (msg.query_params && Object.keys(msg.query_params).length) {
			this.render_save_control($m, msg);
		}
	}

	render_save_control($m, msg) {
		if (msg.savable) {
			const $btn = $(
				`<button class="btn btn-xs btn-default ai-save">${__("Save as Report")}</button>`
			).appendTo($m);
			$btn.on("click", () =>
				frappe.show_alert({
					message: __("Saving as a native Report arrives in Phase 4."),
					indicator: "blue",
				})
			);
		} else if (msg.query_params.group_by) {
			$(
				`<div class="text-muted small">${__(
					"This breakdown can’t be saved as a native report yet — it needs grouping. You can still export the result."
				)}</div>`
			).appendTo($m);
		}
	}

	render_table(columns, rows) {
		const head = columns.map((c) => `<th>${frappe.utils.escape_html(c)}</th>`).join("");
		const body = rows
			.map((row) => {
				const tds = columns
					.map((c) => {
						let v = row[c];
						if (v === null || v === undefined) v = "";
						return `<td>${frappe.utils.escape_html(String(v))}</td>`;
					})
					.join("");
				return `<tr>${tds}</tr>`;
			})
			.join("");
		return `<div class="ai-table-wrap"><table class="table table-bordered ai-table">
			<thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
	}

	add_message(role, html) {
		const $m = $(`<div class="ai-msg ai-msg-${role}">${html}</div>`).appendTo(this.$log);
		this.$log.scrollTop(this.$log[0].scrollHeight);
		return $m;
	}

	inject_styles() {
		if (document.getElementById("ai-assistant-styles")) return;
		$(`<style id="ai-assistant-styles">
			.ai-assistant { max-width: 820px; margin: 0 auto; }
			.ai-chat-log { min-height: 300px; max-height: 60vh; overflow-y: auto;
				padding: 8px 0; }
			.ai-msg { padding: 10px 14px; border-radius: 10px; margin: 8px 0;
				max-width: 90%; white-space: normal; }
			.ai-msg-user { background: var(--bg-blue, #e7f0ff); margin-left: auto; }
			.ai-msg-assistant { background: var(--bg-light-gray, #f4f5f6); }
			.ai-input-row { display: flex; gap: 8px; align-items: flex-end;
				margin-top: 8px; }
			.ai-input { resize: vertical; }
			.ai-error { color: var(--red-600, #c0392b); font-weight: 500; }
			.ai-table-wrap { overflow-x: auto; margin-top: 8px; }
			.ai-table { font-size: 12px; margin: 0; }
			.ai-save { margin-top: 8px; }
			.ai-hint { margin-top: 6px; }
		</style>`).appendTo(document.head);
	}
}
