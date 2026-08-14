<template>
	<div class="ai-msg" :class="`ai-msg-${msg.role}`">
		<div v-if="msg.role === 'assistant'" class="ai-avatar">AI</div>

		<div class="ai-bubble">
			<!-- error -->
			<div v-if="msg.error" class="ai-error">
				{{ msg.error === "permission_denied"
					? __("You don’t have permission to read that data.")
					: __("This query couldn’t be run.") }}
			</div>

			<!-- text -->
			<div v-if="msg.answer" class="ai-text" v-html="asHtml(msg.answer)"></div>
			<div v-else-if="msg.loading" class="ai-typing"><span></span><span></span><span></span></div>

			<!-- data table -->
			<div v-if="msg.rows && msg.rows.length" class="ai-table-wrap">
				<table class="ai-table">
					<thead>
						<tr><th v-for="c in msg.columns" :key="c">{{ c }}</th></tr>
					</thead>
					<tbody>
						<tr v-for="(row, i) in msg.rows" :key="i">
							<td v-for="c in msg.columns" :key="c">{{ cell(row[c]) }}</td>
						</tr>
					</tbody>
				</table>
			</div>

			<div v-if="msg.row_truncated || msg.col_truncated" class="ai-note">
				{{ __("Results were truncated for display.") }}
			</div>

			<!-- doc sources -->
			<div v-if="msg.sources && msg.sources.length" class="ai-note">
				{{ __("Sources:") }} {{ Array.isArray(msg.sources) ? msg.sources.join(", ") : msg.sources }}
			</div>

			<!-- insights -->
			<div v-if="msg.insights" class="ai-insights" v-html="asHtml(msg.insights)"></div>

			<!-- actions -->
			<div v-if="showActions" class="ai-actions">
				<button v-if="!msg.saved" class="ai-chip" :disabled="busy" @click="$emit('save', msg)">
					{{ __("Save as Report") }}
				</button>
				<span v-else class="ai-saved">
					{{ __("Saved:") }}
					<a :href="msg.saved.url">{{ msg.saved.title }}</a>
					<template v-if="msg.saved.native_url"> · <a :href="msg.saved.native_url">{{ __("native") }}</a></template>
				</span>
				<button v-if="!msg.insights" class="ai-chip" :disabled="busy" @click="$emit('insights', msg)">
					✨ {{ __("Insights") }}
				</button>
			</div>
		</div>
	</div>
</template>

<script>
export default {
	name: "ChatMessage",
	props: {
		msg: { type: Object, required: true },
		busy: { type: Boolean, default: false },
	},
	emits: ["save", "insights"],
	data() {
		return { __: window.__ };
	},
	computed: {
		showActions() {
			return this.msg.role === "assistant" && this.msg.query_params
				&& Object.keys(this.msg.query_params).length && !this.msg.error;
		},
	},
	methods: {
		asHtml(t) {
			return frappe.utils.escape_html(t || "").replace(/\n/g, "<br>");
		},
		cell(v) {
			return v === null || v === undefined ? "" : String(v);
		},
	},
};
</script>

<style scoped>
.ai-msg { display: flex; gap: 10px; margin: 14px 0; }
.ai-msg-user { justify-content: flex-end; }
.ai-avatar {
	width: 28px; height: 28px; border-radius: 50%; flex: 0 0 28px;
	background: var(--ai-accent); color: var(--ai-on-accent); font-size: 11px; font-weight: 700;
	display: flex; align-items: center; justify-content: center;
}
.ai-bubble {
	max-width: 80%; padding: 12px 14px; border-radius: 12px;
	background: var(--ai-assistant-bubble); color: var(--ai-text); font-size: 14px; line-height: 1.5;
}
.ai-msg-user .ai-bubble { background: var(--ai-user-bubble); color: var(--ai-on-accent); }
.ai-error { color: #ef4444; font-weight: 500; }
.ai-table-wrap { overflow-x: auto; margin-top: 10px; border: 1px solid var(--ai-border); border-radius: 8px; }
.ai-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.ai-table th, .ai-table td { padding: 6px 10px; border-bottom: 1px solid var(--ai-border); text-align: left; white-space: nowrap; }
.ai-table th { background: var(--ai-hover); color: var(--ai-text); font-weight: 600; position: sticky; top: 0; }
.ai-table td { color: var(--ai-text); }
.ai-table tr:last-child td { border-bottom: none; }
.ai-note { color: var(--ai-muted); font-size: 12px; margin-top: 8px; }
.ai-insights { margin-top: 10px; padding: 10px 12px; background: var(--ai-insight); color: var(--ai-text); border-radius: 8px; font-size: 13px; }
.ai-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 10px; }
.ai-chip {
	border: 1px solid var(--ai-border); background: var(--ai-surface); color: var(--ai-text);
	border-radius: 999px; padding: 4px 12px; font-size: 12px; cursor: pointer; transition: all 0.12s;
}
.ai-chip:hover:not(:disabled) { background: var(--ai-hover); border-color: var(--ai-accent); }
.ai-chip:disabled { opacity: 0.5; cursor: default; }
.ai-saved { font-size: 12px; }
.ai-saved a { color: var(--ai-accent); }
.ai-typing span {
	display: inline-block; width: 6px; height: 6px; margin-right: 3px; border-radius: 50%;
	background: var(--ai-muted); animation: ai-blink 1.2s infinite both;
}
.ai-typing span:nth-child(2) { animation-delay: 0.2s; }
.ai-typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes ai-blink { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }
</style>
