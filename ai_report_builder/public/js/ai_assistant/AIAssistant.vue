<template>
	<div class="ai-app">
		<ChatSidebar
			:sessions="sessions"
			:active-session="session"
			:mode="mode"
			@new-chat="newChat"
			@set-mode="setMode"
			@open="openSession"
			@delete="deleteSession"
		/>

		<main class="ai-chat">
			<div ref="log" class="ai-log">
				<div v-if="!messages.length" class="ai-hero">
					<h2>{{ mode === "Docs" ? __("Ask the ERPNext docs") : __("Ask about your data") }}</h2>
					<p class="text-muted">{{ heroHint }}</p>
					<div class="ai-suggest">
						<button v-for="s in suggestions" :key="s" class="ai-sugg" @click="send(s)">{{ s }}</button>
					</div>
				</div>

				<ChatMessage
					v-for="(m, i) in messages"
					:key="i"
					:msg="m"
					:busy="busy"
					@save="saveReport"
					@insights="getInsights"
				/>
			</div>

			<div class="ai-composer">
				<textarea
					ref="input"
					v-model="draft"
					rows="1"
					class="ai-input"
					:placeholder="placeholder"
					@keydown.enter.exact.prevent="send()"
				></textarea>
				<button class="ai-send" :disabled="busy || !draft.trim()" @click="send()">
					{{ __("Send") }}
				</button>
			</div>
			<div class="ai-foot text-muted">{{ __("Read-only. Queries respect your ERPNext permissions.") }}</div>
		</main>
	</div>
</template>

<script>
import ChatSidebar from "./ChatSidebar.vue";
import ChatMessage from "./ChatMessage.vue";
import { API } from "./api.js";

export default {
	name: "AIAssistant",
	components: { ChatSidebar, ChatMessage },
	data() {
		return {
			__: window.__,
			mode: "Data",
			session: null,
			sessions: [],
			messages: [],
			draft: "",
			busy: false,
		};
	},
	computed: {
		placeholder() {
			return this.mode === "Docs"
				? __("Ask a how-to question, e.g. “how do I create a purchase order?”")
				: __("Ask a business question, e.g. “total sales last month”");
		},
		heroHint() {
			return this.mode === "Docs"
				? __("Answers from the ERPNext manual, with sources.")
				: __("Natural-language questions over your live ERPNext data.");
		},
		suggestions() {
			return this.mode === "Docs"
				? [__("How do I create a purchase order?"), __("How do I record a payment?"), __("How do I schedule a report?")]
				: [__("Show unpaid invoices"), __("Total sales last month"), __("Count invoices by status")];
		},
	},
	mounted() {
		this.loadSessions();
	},
	methods: {
		async loadSessions() {
			this.sessions = (await API.listSessions(this.mode)) || [];
		},
		setMode(m) {
			if (m === this.mode) return;
			this.mode = m;
			this.newChat();
			this.loadSessions();
		},
		newChat() {
			this.session = null;
			this.messages = [];
		},
		async openSession(session) {
			this.session = session;
			const msgs = (await API.getMessages(session)) || [];
			this.messages = msgs.map((m) => ({
				role: m.role,
				answer: m.content,
				query_params: m.query_params,
				savable: m.savable,
				sources: m.sources,
			}));
			this.scroll();
		},
		async deleteSession(session) {
			await API.deleteSession(session);
			if (session === this.session) this.newChat();
			this.loadSessions();
		},
		scroll() {
			this.$nextTick(() => {
				const el = this.$refs.log;
				if (el) el.scrollTop = el.scrollHeight;
			});
		},
		async send(text) {
			const question = (text || this.draft).trim();
			if (!question || this.busy) return;
			this.draft = "";
			this.messages.push({ role: "user", answer: question });
			this.messages.push({ role: "assistant", loading: true });
			const idx = this.messages.length - 1;
			this.busy = true;
			this.scroll();

			try {
				const fn = this.mode === "Docs" ? API.askDocs : API.ask;
				const res = await fn(question, this.session);
				this.session = res.session || this.session;
				// Replace the placeholder reactively (Vue 3 tracks index assignment)
				// so computed props like showActions re-evaluate.
				this.messages[idx] = { role: "assistant", loading: false, ...res };
				this.loadSessions();
			} catch (e) {
				this.messages[idx] = {
					role: "assistant",
					loading: false,
					error: "execution_error",
					answer: __("Something went wrong. Check AI Assistant Settings."),
				};
			} finally {
				this.busy = false;
				this.scroll();
			}
		},
		async getInsights(msg) {
			this.busy = true;
			try {
				const res = await API.insights(msg.query_params, msg.answer || "");
				msg.insights = res.insights || __("No insights available right now.");
			} finally {
				this.busy = false;
				this.scroll();
			}
		},
		async saveReport(msg) {
			this.busy = true;
			try {
				const res = await API.saveReport(msg.query_params, msg.answer || "");
				msg.saved = { title: res.title || res.name, url: res.url, native_url: res.native_url };
				frappe.show_alert({ message: __("Report saved."), indicator: "green" });
			} finally {
				this.busy = false;
			}
		},
	},
};
</script>

<style scoped>
/* Deep-navy theme with a subtle diagonal line pattern (from the reference art).
   Fixed dark palette; child components inherit these variables. */
.ai-app {
	--ai-navy-deep: #082031;
	--ai-navy: #0a2537;
	--ai-line: rgba(70, 140, 170, 0.10);
	--ai-accent: #2e90b4;
	--ai-accent-hover: #39a8cf;
	--ai-on-accent: #ffffff;
	--ai-user-bubble: #1f6f8b;
	--ai-assistant-bubble: #0f2f45;
	--ai-bg: #0a2537;
	--ai-surface: #0e2c40;
	--ai-text: #e3edf5;
	--ai-muted: #89a6ba;
	--ai-border: #1b3d52;
	--ai-insight: #0e3a52;
	--ai-active: #14405a;
	--ai-hover: #103046;

	display: flex;
	height: calc(100vh - var(--navbar-height, 60px) - 40px);
	color: var(--ai-text);
	border: 1px solid var(--ai-border);
	border-radius: 12px;
	overflow: hidden;
	background-color: var(--ai-navy);
	background-image: repeating-linear-gradient(
		115deg,
		transparent 0 62px,
		var(--ai-line) 62px 63px
	);
}
.ai-chat { flex: 1; display: flex; flex-direction: column; min-width: 0; background: transparent; }
.ai-log { flex: 1; overflow-y: auto; padding: 8px 24px; max-width: 900px; margin: 0 auto; width: 100%; }
.ai-hero { text-align: center; margin-top: 12vh; }
.ai-hero h2 { margin-bottom: 6px; color: var(--ai-text); }
.ai-hero .text-muted { color: var(--ai-muted); }
.ai-suggest { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 18px; }
.ai-sugg {
	border: 1px solid var(--ai-border); background: var(--ai-surface); color: var(--ai-text);
	border-radius: 999px; padding: 8px 16px; font-size: 13px; cursor: pointer; transition: all 0.12s;
}
.ai-sugg:hover { background: var(--ai-hover); border-color: var(--ai-accent); }
.ai-composer {
	display: flex; gap: 8px; align-items: flex-end; padding: 12px 24px 4px;
	max-width: 900px; margin: 0 auto; width: 100%;
}
.ai-input {
	flex: 1; resize: none; border: 1px solid var(--ai-border); border-radius: 10px;
	padding: 10px 14px; font-size: 14px; max-height: 160px;
	background: var(--ai-surface); color: var(--ai-text);
}
.ai-input:focus { outline: none; border-color: var(--ai-accent); box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.15); }
.ai-send {
	border: none; background: var(--ai-accent); color: var(--ai-on-accent); border-radius: 10px;
	padding: 10px 18px; font-weight: 500; cursor: pointer; transition: background 0.12s;
}
.ai-send:hover:not(:disabled) { background: var(--ai-accent-hover); }
.ai-send:disabled { opacity: 0.5; cursor: default; }
.ai-foot { text-align: center; font-size: 12px; padding: 4px 0 10px; color: var(--ai-muted); }
</style>
