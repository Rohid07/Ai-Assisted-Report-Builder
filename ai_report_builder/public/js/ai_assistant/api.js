// Thin wrapper around frappe.xcall so components stay clean.
export function call(method, args = {}) {
	return frappe.xcall(method, args);
}

export const API = {
	ask: (question, session) => call("ai_report_builder.api.ask", { question, session }),
	askDocs: (question, session) => call("ai_report_builder.api.ask_docs", { question, session }),
	insights: (query_params, question) =>
		call("ai_report_builder.api.insights", { query_params: JSON.stringify(query_params), question }),
	saveReport: (query_params, question) =>
		call("ai_report_builder.ai.report_view.save_ai_report", {
			query_params: JSON.stringify(query_params),
			question,
		}),
	listSessions: (kind) => call("ai_report_builder.ai.chat.list_sessions", { kind }),
	getMessages: (session) => call("ai_report_builder.ai.chat.get_session_messages", { session }),
	deleteSession: (session) => call("ai_report_builder.ai.chat.delete_session", { session }),
};
