import { createApp } from "vue";
import AIAssistant from "./ai_assistant/AIAssistant.vue";

frappe.provide("frappe.ai_assistant");

frappe.ai_assistant.mount = function (el) {
	const app = createApp(AIAssistant);
	app.mount(el);
	return app;
};
