// Bundle Monaco locally (no CDN) so the editor works offline and under a strict Content-Security-Policy.
// Only the editor core + Monarch syntax highlighters are loaded: no TypeScript language service, so one
// small worker is enough.
import { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/esm/vs/editor/edcore.main.js";
import "monaco-editor/esm/vs/basic-languages/python/python.contribution.js";
import "monaco-editor/esm/vs/basic-languages/java/java.contribution.js";
import "monaco-editor/esm/vs/basic-languages/cpp/cpp.contribution.js";
import "monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution.js";
import EditorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };

monaco.editor.defineTheme("cg-dark", {
  base: "vs-dark", inherit: true, rules: [{ token: "comment", foreground: "6b7389", fontStyle: "italic" }],
  colors: { "editor.background": "#0f1218", "editor.lineHighlightBackground": "#171b24", "editorLineNumber.foreground": "#3d4456",
    "editorLineNumber.activeForeground": "#9aa3b8", "editorGutter.background": "#0f1218", "editor.selectionBackground": "#3b3f6e88",
    "scrollbarSlider.background": "#ffffff14", "scrollbarSlider.hoverBackground": "#ffffff24", "editorWidget.background": "#161a23" },
});
monaco.editor.defineTheme("cg-light", {
  base: "vs", inherit: true, rules: [{ token: "comment", foreground: "8a93a6", fontStyle: "italic" }],
  colors: { "editor.background": "#ffffff", "editor.lineHighlightBackground": "#f4f6fb", "editorLineNumber.foreground": "#c0c6d4",
    "editorGutter.background": "#ffffff" },
});

loader.config({ monaco });
export { monaco };
