frappe.pages["ai-assistant"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("AI Assistant"),
		single_column: true,
	});

	page.add_inner_button(__("My Reports"), () => frappe.set_route("List", "AI Report"));
	page.add_inner_button(__("Settings"), () =>
		frappe.set_route("Form", "AI Assistant Settings", "AI Assistant Settings")
	);

	// Give the Vue app the full width of the page body.
	const container = document.createElement("div");
	container.style.height = "100%";
	page.main.empty().append(container);
	page.main.css({ "margin-top": 0, padding: 0 });

	frappe.require("ai_assistant.bundle.js").then(() => {
		frappe.ai_assistant.mount(container);
	});
};
