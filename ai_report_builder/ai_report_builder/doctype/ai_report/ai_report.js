// Copyright (c) 2026, rohid and contributors
// For license information, please see license.txt

frappe.ui.form.on("AI Report", {
	refresh(frm) {
		if (frm.doc.name && !frm.is_new()) {
			frm.page.set_primary_action(__("Open Report"), () => {
				window.location.assign(
					`/app/ai-report-view?name=${encodeURIComponent(frm.doc.name)}`
				);
			});
		}
	},
});
