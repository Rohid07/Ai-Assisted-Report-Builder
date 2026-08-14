<template>
	<aside class="ai-sidebar">
		<button class="ai-new-btn" @click="$emit('new-chat')">
			<span class="ai-plus">+</span> {{ __("New chat") }}
		</button>

		<div class="ai-mode">
			<button
				v-for="m in modes"
				:key="m"
				class="ai-mode-tab"
				:class="{ active: mode === m }"
				@click="$emit('set-mode', m)"
			>
				{{ m === "Data" ? __("Data") : __("How-to Docs") }}
			</button>
		</div>

		<div class="ai-sessions">
			<div v-if="!sessions.length" class="ai-empty">{{ __("No past chats yet.") }}</div>
			<div
				v-for="s in sessions"
				:key="s.session"
				class="ai-session"
				:class="{ active: s.session === activeSession }"
				@click="$emit('open', s.session)"
			>
				<span class="ai-session-title">{{ s.title || __("Chat") }}</span>
				<span class="ai-session-del" :title="__('Delete')" @click.stop="$emit('delete', s.session)">×</span>
			</div>
		</div>

		<div class="ai-side-foot">
			<a href="/app/ai-report-view">{{ __("My reports →") }}</a>
		</div>
	</aside>
</template>

<script>
export default {
	name: "ChatSidebar",
	props: {
		sessions: { type: Array, default: () => [] },
		activeSession: { type: String, default: null },
		mode: { type: String, default: "Data" },
	},
	emits: ["new-chat", "set-mode", "open", "delete"],
	data() {
		return { modes: ["Data", "Docs"], __: window.__ };
	},
};
</script>

<style scoped>
.ai-sidebar {
	width: 260px;
	flex: 0 0 260px;
	display: flex;
	flex-direction: column;
	border-right: 1px solid var(--ai-border);
	padding: 12px;
	gap: 10px;
	height: 100%;
	background: var(--ai-navy-deep, #082031);
}
.ai-new-btn {
	border: 1px solid var(--ai-border);
	background: var(--ai-surface);
	color: var(--ai-text);
	border-radius: 8px;
	padding: 8px 12px;
	font-weight: 500;
	cursor: pointer;
	text-align: left;
	transition: all 0.12s;
}
.ai-new-btn:hover { background: var(--ai-hover); border-color: var(--ai-accent); }
.ai-plus { font-weight: 700; margin-right: 4px; color: var(--ai-accent); }
.ai-mode { display: flex; background: var(--ai-hover); border-radius: 8px; padding: 3px; }
.ai-mode-tab {
	flex: 1;
	border: none;
	background: transparent;
	border-radius: 6px;
	padding: 6px 8px;
	font-size: 12px;
	cursor: pointer;
	color: var(--ai-muted);
}
.ai-mode-tab.active { background: var(--ai-surface); color: var(--ai-accent); box-shadow: 0 1px 2px rgba(0,0,0,0.08); font-weight: 600; }
.ai-sessions { flex: 1; overflow-y: auto; margin-top: 4px; }
.ai-empty { color: var(--ai-muted); font-size: 12px; padding: 8px; }
.ai-session {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 8px 10px;
	border-radius: 8px;
	cursor: pointer;
	font-size: 13px;
	color: var(--ai-text);
}
.ai-session:hover { background: var(--ai-hover); }
.ai-session.active { background: var(--ai-active); color: var(--ai-accent); }
.ai-session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ai-session-del { color: var(--ai-muted); opacity: 0.5; padding-left: 8px; }
.ai-session-del:hover { opacity: 1; color: #ef4444; }
.ai-side-foot { border-top: 1px solid var(--ai-border); padding-top: 10px; font-size: 13px; }
.ai-side-foot a { color: var(--ai-accent); }
</style>
