// Copyright (c) 2026, rohid and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Assistant Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Open AI Assistant"), () => {
			frappe.set_route("ai-assistant");
		});

		frm.add_custom_button(__("Test Connection"), () => {
			frappe.dom.freeze(__("Pinging {0}…", [frm.doc.active_provider]));
			frappe
				.call({
					method: "ai_report_builder.api.test_connection",
					args: { provider: frm.doc.active_provider },
				})
				.then((r) => {
					frappe.dom.unfreeze();
					if (r.message && r.message.ok) {
						frappe.msgprint({
							title: __("Connection OK"),
							indicator: "green",
							message: __("Provider {0} responded (model {1}).", [
								frm.doc.active_provider,
								r.message.model,
							]),
						});
					}
				})
				.catch(() => frappe.dom.unfreeze());
		});
	},
});
