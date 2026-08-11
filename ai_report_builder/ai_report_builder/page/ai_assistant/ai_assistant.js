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
		this.mode = "Data";
		this.session = null;
		this.render();
		this.load_sessions();
	}

	render() {
		this.wrapper = $(`
			<div class="ai-assistant">
				<div class="ai-sidebar">
					<button class="btn btn-primary btn-sm btn-block ai-new">${__("+ New Chat")}</button>
					<div class="ai-mode btn-group btn-group-sm btn-block">
						<button class="btn btn-default active" data-mode="Data">${__("Data")}</button>
						<button class="btn btn-default" data-mode="Docs">${__("How-to Docs")}</button>
					</div>
					<div class="ai-sessions" data-sessions></div>
				</div>
				<div class="ai-main">
					<div class="ai-chat-log" data-log></div>
					<div class="ai-input-row">
						<textarea class="form-control ai-input" rows="1"
							placeholder="${__("Ask a business question…")}"></textarea>
						<button class="btn btn-primary ai-send">${__("Ask")}</button>
					</div>
					<div class="ai-hint text-muted small">
						${__("Read-only. Queries respect your ERPNext permissions.")}
					</div>
				</div>
			</div>
		`).appendTo(this.page.main);

		this.$log = this.wrapper.find("[data-log]");
		this.$input = this.wrapper.find(".ai-input");
		this.$send = this.wrapper.find(".ai-send");
		this.$sessions = this.wrapper.find("[data-sessions]");

		this.inject_styles();

		this.$send.on("click", () => this.ask());
		this.$input.on("keydown", (e) => {
			if (e.key === "Enter" && !e.shiftKey) {
				e.preventDefault();
				this.ask();
			}
		});
		this.wrapper.find(".ai-new").on("click", () => this.new_chat());
		this.wrapper.find(".ai-mode .btn").on("click", (e) => {
			const $b = $(e.currentTarget);
			this.mode = $b.data("mode");
			this.wrapper.find(".ai-mode .btn").removeClass("active");
			$b.addClass("active");
			this.$input.attr(
				"placeholder",
				this.mode === "Docs"
					? __("Ask a how-to question, e.g. “how do I create a purchase order?”")
					: __("Ask a business question, e.g. “total sales last month”")
			);
			this.new_chat();
			this.load_sessions();
		});
	}

	// ---- sessions ----
	load_sessions() {
		frappe.call({
			method: "ai_report_builder.ai.chat.list_sessions",
			args: { kind: this.mode },
			callback: (r) => this.render_sessions(r.message || []),
		});
	}

	render_sessions(sessions) {
		this.$sessions.empty();
		if (!sessions.length) {
			this.$sessions.append(`<div class="text-muted small ai-empty">${__("No past chats yet.")}</div>`);
			return;
		}
		sessions.forEach((s) => {
			const active = s.session === this.session ? " active" : "";
			const $row = $(`
				<div class="ai-session${active}" data-id="${s.session}">
					<span class="ai-session-title">${frappe.utils.escape_html(s.title || __("Chat"))}</span>
					<span class="ai-session-del" title="${__("Delete")}">&times;</span>
				</div>
			`).appendTo(this.$sessions);
			$row.find(".ai-session-title").on("click", () => this.open_session(s.session));
			$row.find(".ai-session-del").on("click", (e) => {
				e.stopPropagation();
				this.delete_session(s.session);
			});
		});
	}

	open_session(session) {
		this.session = session;
		frappe.call({
			method: "ai_report_builder.ai.chat.get_session_messages",
			args: { session },
			callback: (r) => {
				this.$log.empty();
				(r.message || []).forEach((m) => this.render_stored(m));
				this.load_sessions();
			},
		});
	}

	delete_session(session) {
		frappe.call({
			method: "ai_report_builder.ai.chat.delete_session",
			args: { session },
			callback: () => {
				if (session === this.session) this.new_chat();
				this.load_sessions();
			},
		});
	}

	new_chat() {
		this.session = null;
		this.$log.empty();
		this.load_sessions();
	}

	// ---- asking ----
	ask() {
		const question = (this.$input.val() || "").trim();
		if (!question) return;
		this.lastQuestion = question;
		this.$input.val("");
		this.add_message("user", frappe.utils.escape_html(question));

		const $thinking = this.add_message("assistant", `<span class="text-muted">${__("Thinking…")}</span>`);
		this.$send.prop("disabled", true);

		const on_error = () => {
			$thinking.remove();
			this.add_message("assistant", `<div class="ai-error">${__("Something went wrong. Check AI Assistant Settings (API key / provider).")}</div>`);
		};
		const done = () => this.$send.prop("disabled", false);
		const method = this.mode === "Docs" ? "ai_report_builder.api.ask_docs" : "ai_report_builder.api.ask";

		frappe.call({
			method,
			args: { question, session: this.session },
			callback: (r) => {
				$thinking.remove();
				if (!r.message) return;
				this.session = r.message.session || this.session;
				if (this.mode === "Docs") this.render_doc_answer(r.message);
				else this.render_answer(r.message);
				this.load_sessions();
			},
			error: on_error,
			always: done,
		});
	}

	// ---- rendering ----
	render_answer(msg) {
		const parts = [];
		if (msg.error) {
			const label = msg.error === "permission_denied"
				? __("You don’t have permission to read that data.")
				: __("This query couldn’t be run.");
			parts.push(`<div class="ai-error">${label}</div>`);
		}
		if (msg.answer) parts.push(this._text(msg.answer));
		if (msg.rows && msg.rows.length) parts.push(this.render_table(msg.columns, msg.rows));
		else if (!msg.error && !msg.answer) parts.push(`<div class="text-muted">${__("No results.")}</div>`);
		if (msg.row_truncated || msg.col_truncated) parts.push(`<div class="text-muted small">${__("Results were truncated for display.")}</div>`);

		const $m = this.add_message("assistant", parts.join(""));
		if (msg.query_params && Object.keys(msg.query_params).length) {
			this.render_save_control($m, msg);
			if (msg.rows && msg.rows.length) this.render_insights_control($m, msg);
		}
	}

	render_doc_answer(msg) {
		const parts = [];
		if (msg.answer) parts.push(this._text(msg.answer));
		else if (msg.error) parts.push(`<div class="ai-error">${__("The docs assistant is unavailable right now.")}</div>`);
		if (msg.sources && msg.sources.length) {
			const srcs = (Array.isArray(msg.sources) ? msg.sources : [msg.sources]).map((s) => frappe.utils.escape_html(s)).join(", ");
			parts.push(`<div class="text-muted small">${__("Sources:")} ${srcs}</div>`);
		}
		this.add_message("assistant", parts.join("") || __("No documentation found."));
	}

	// Render a message loaded from history.
	render_stored(m) {
		if (m.role === "user") {
			this.add_message("user", frappe.utils.escape_html(m.content));
			return;
		}
		const parts = [this._text(m.content || "")];
		if (m.sources) parts.push(`<div class="text-muted small">${__("Sources:")} ${frappe.utils.escape_html(m.sources)}</div>`);
		const $m = this.add_message("assistant", parts.join(""));
		if (m.query_params && Object.keys(m.query_params).length) {
			this.render_save_control($m, { savable: m.savable, query_params: m.query_params });
		}
	}

	_text(t) {
		return `<div class="ai-text">${frappe.utils.escape_html(t).replace(/\n/g, "<br>")}</div>`;
	}

	render_save_control($m, msg) {
		if (msg.savable) {
			const $btn = $(`<button class="btn btn-xs btn-default ai-save">${__("Save as Report")}</button>`).appendTo($m);
			$btn.on("click", () => this.save_report($btn, msg));
		} else if (msg.query_params && msg.query_params.group_by) {
			$(`<div class="text-muted small">${__("This breakdown can’t be saved as a native report — it needs grouping. You can still export the result.")}</div>`).appendTo($m);
		}
	}

	render_insights_control($m, msg) {
		const $btn = $(`<button class="btn btn-xs btn-default ai-insights">${__("✨ Insights")}</button>`).appendTo($m);
		$btn.on("click", () => {
			$btn.prop("disabled", true).text(__("Analysing…"));
			frappe.call({
				method: "ai_report_builder.api.insights",
				args: { query_params: msg.query_params, question: this.lastQuestion || "" },
				callback: (r) => {
					const res = r.message || {};
					$btn.remove();
					const text = res.insights ? frappe.utils.escape_html(res.insights).replace(/\n/g, "<br>") : __("No insights available right now.");
					$(`<div class="ai-insights-box">${text}</div>`).appendTo($m);
				},
				error: () => $btn.prop("disabled", false).text(__("✨ Insights")),
			});
		});
	}

	save_report($btn, msg) {
		$btn.prop("disabled", true).text(__("Saving…"));
		frappe.call({
			method: "ai_report_builder.api.save_report",
			args: { query_params: msg.query_params, question: this.lastQuestion || "" },
			callback: (r) => {
				const res = r.message || {};
				$btn.replaceWith(`<div class="ai-saved">${__("Saved as report:")} <a href="${res.url}" target="_blank">${frappe.utils.escape_html(res.report_name)}</a></div>`);
				frappe.show_alert({ message: __("Report saved."), indicator: "green" });
			},
			error: () => $btn.prop("disabled", false).text(__("Save as Report")),
		});
	}

	render_table(columns, rows) {
		const head = columns.map((c) => `<th>${frappe.utils.escape_html(c)}</th>`).join("");
		const body = rows.map((row) => {
			const tds = columns.map((c) => {
				let v = row[c];
				if (v === null || v === undefined) v = "";
				return `<td>${frappe.utils.escape_html(String(v))}</td>`;
			}).join("");
			return `<tr>${tds}</tr>`;
		}).join("");
		return `<div class="ai-table-wrap"><table class="table table-bordered ai-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
	}

	add_message(role, html) {
		const $m = $(`<div class="ai-msg ai-msg-${role}">${html}</div>`).appendTo(this.$log);
		this.$log.scrollTop(this.$log[0].scrollHeight);
		return $m;
	}

	inject_styles() {
		if (document.getElementById("ai-assistant-styles")) return;
		$(`<style id="ai-assistant-styles">
			.ai-assistant { display: flex; gap: 16px; max-width: 1100px; margin: 0 auto; }
			.ai-sidebar { width: 230px; flex: 0 0 230px; }
			.ai-sidebar .ai-mode { display: flex; width: 100%; margin: 8px 0; }
			.ai-sidebar .ai-mode .btn { flex: 1; }
			.ai-sessions { margin-top: 6px; max-height: 60vh; overflow-y: auto; }
			.ai-session { display: flex; justify-content: space-between; align-items: center;
				padding: 6px 8px; border-radius: 6px; cursor: pointer; font-size: 13px; }
			.ai-session:hover { background: var(--bg-light-gray, #f4f5f6); }
			.ai-session.active { background: var(--bg-blue, #e7f0ff); }
			.ai-session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
			.ai-session-del { color: var(--text-muted); padding-left: 6px; opacity: 0.5; }
			.ai-session-del:hover { opacity: 1; color: var(--red-600, #c0392b); }
			.ai-empty { padding: 8px; }
			.ai-main { flex: 1; min-width: 0; }
			.ai-chat-log { min-height: 320px; max-height: 62vh; overflow-y: auto; padding: 8px 0; }
			.ai-msg { padding: 10px 14px; border-radius: 10px; margin: 8px 0; max-width: 92%; }
			.ai-msg-user { background: var(--bg-blue, #e7f0ff); margin-left: auto; }
			.ai-msg-assistant { background: var(--bg-light-gray, #f4f5f6); }
			.ai-input-row { display: flex; gap: 8px; align-items: flex-end; margin-top: 8px; }
			.ai-input { resize: vertical; }
			.ai-error { color: var(--red-600, #c0392b); font-weight: 500; }
			.ai-table-wrap { overflow-x: auto; margin-top: 8px; }
			.ai-table { font-size: 12px; margin: 0; }
			.ai-save, .ai-insights { margin-top: 8px; margin-right: 6px; }
			.ai-insights-box { margin-top: 8px; padding: 8px 10px; background: var(--bg-blue, #eef4ff); border-radius: 8px; font-size: 13px; }
			.ai-saved { margin-top: 8px; }
			.ai-hint { margin-top: 6px; }
		</style>`).appendTo(document.head);
	}
}
