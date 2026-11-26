export const LANG_LABEL = { python: "Python", java: "Java", c: "C", cpp: "C++", javascript: "JavaScript" };
const EXT = { py: "python", java: "java", c: "c", h: "c", cc: "cpp", cpp: "cpp", cxx: "cpp", hpp: "cpp", js: "javascript", mjs: "javascript", jsx: "javascript" };
export const ACCEPT = ".py,.java,.c,.h,.cpp,.cc,.cxx,.hpp,.js,.mjs,.jsx";
export const MONACO_LANG = { python: "python", java: "java", c: "cpp", cpp: "cpp", javascript: "javascript" };

export const extOf = (name) => (name.includes(".") ? name.split(".").pop().toLowerCase() : "");
export const langOf = (name) => EXT[extOf(name)] || "python";
export const isSupported = (name) => !!EXT[extOf(name)];
export const pct = (x, d = 0) => (x == null || Number.isNaN(x) ? "–" : `${(x * 100).toFixed(d)}%`);
export const cap = (s) => (s ? String(s)[0].toUpperCase() + String(s).slice(1) : s);
export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));

export function fmtDate(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return d < 30 ? `${d} d ago` : fmtDate(iso);
}

export function download(filename, text, type = "application/json") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Make `name` unique among `taken` by appending _2, _3 … before the extension. */
export function uniqueName(name, taken) {
  if (!taken.has(name)) return name;
  const dot = name.lastIndexOf(".");
  const stem = dot > 0 ? name.slice(0, dot) : name, ext = dot > 0 ? name.slice(dot) : "";
  for (let i = 2; ; i++) if (!taken.has(`${stem}_${i}${ext}`)) return `${stem}_${i}${ext}`;
}

export const LEVEL = {
  clear: { label: "Clear", title: "No flags raised", tone: "good" },
  attention: { label: "Attention", title: "One signal needs a look", tone: "warn" },
  review: { label: "Review", title: "Several signals — review manually", tone: "bad" },
};
export const RISK_TONE = { none: "good", low: "good", medium: "warn", high: "bad", critical: "bad" };
export const SEV_ORDER = ["critical", "high", "medium", "low"];

/** Pairs involving `name` (optionally restricted to one selected pair). */
export function pairsFor(report, name, selected) {
  const pairs = report?.plagiarism?.pairs || [];
  if (selected) return pairs.filter((p) => p.a === selected[0] && p.b === selected[1]).filter((p) => p.a === name || p.b === name);
  return pairs.filter((p) => p.flagged && (p.a === name || p.b === name));
}

// ------------------------------------------------------------------------------------------ demo data
const PY_HUMAN = `import math

def circle_area(r):
    # area of a circle
    total = math.pi * r * r
    return round(total, 2)

def collatz(n):
    steps = 0
    while n != 1:
        if n % 2 == 0:
            n //= 2
        else:
            n = 3 * n + 1
        steps += 1
    return steps

def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(collatz(27), fib(10), circle_area(3))
`;

const PY_COPY = `import math

def fibonacci(count):
    x, y = 0, 1
    for _ in range(count):
        x, y = y, x + y
    return x

def collatz_len(num):
    cnt = 0
    unused = 5
    while num != 1:
        if num % 2 == 0:
            num //= 2
        else:
            num = 3 * num + 1
        cnt += 1
    return cnt

def circle(radius):
    t = math.pi * radius * radius
    return round(t, 2)

print(collatz_len(27), fibonacci(10), circle(3))
`;

const PY_AI = `from typing import List


def calculate_collatz_steps(start_value: int) -> int:
    """Return the number of steps needed for a Collatz sequence to reach 1.

    Args:
        start_value: A positive integer that starts the sequence.

    Returns:
        The number of iterations performed.

    Raises:
        ValueError: If the start value is not a positive integer.
    """
    if start_value <= 0:
        raise ValueError("start_value must be a positive integer")

    step_count = 0
    current_value = start_value
    # Apply the Collatz rules until the sequence converges
    while current_value != 1:
        if current_value % 2 == 0:
            current_value //= 2
        else:
            current_value = 3 * current_value + 1
        step_count += 1
    return step_count


def generate_fibonacci_sequence(sequence_length: int) -> List[int]:
    """Generate the first \`sequence_length\` Fibonacci numbers."""
    fibonacci_numbers: List[int] = []
    previous_value, current_value = 0, 1
    for _ in range(sequence_length):
        fibonacci_numbers.append(previous_value)
        previous_value, current_value = current_value, previous_value + current_value
    return fibonacci_numbers


def main() -> None:
    """Entry point demonstrating the helper functions."""
    try:
        print(f"Collatz steps for 27: {calculate_collatz_steps(27)}")
        print(f"First 10 Fibonacci numbers: {generate_fibonacci_sequence(10)}")
    except ValueError as error:
        print(f"Error: {error}")


if __name__ == "__main__":
    main()
`;

const PY_VULN = `import os, pickle, hashlib, sqlite3
import subprocess

API_KEY = "sk_live_51HxQ2bFakeKeyForDemo"

def run(user_input):
    os.system("ls " + user_input)
    return hashlib.md5(user_input.encode()).hexdigest()

def load(blob):
    return pickle.loads(blob)

def find_user(conn, name):
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM users WHERE name = '{name}'")
    return cur.fetchall()

def backup(path):
    subprocess.run(
        "tar czf backup.tgz " + path,
        shell=True,
    )
`;

const JAVA_VULN = `import java.sql.*;
import java.security.MessageDigest;

public class UserDao {
    public ResultSet find(Connection c, String name) throws Exception {
        Statement st = c.createStatement();
        return st.executeQuery("SELECT * FROM users WHERE name = '" + name + "'");
    }

    public byte[] hash(String password) throws Exception {
        MessageDigest md = MessageDigest.getInstance("MD5");
        return md.digest(password.getBytes());
    }

    public void ping(String host) throws Exception {
        Runtime.getRuntime().exec("ping -c 1 " + host);
    }
}
`;

const C_VULN = `#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    char name[16];
    char greeting[32];
    gets(name);
    strcpy(greeting, "Hello ");
    strcat(greeting, name);
    printf(greeting);
    return 0;
}
`;

const JS_VULN = `const express = require('express');
const { exec } = require('child_process');
const app = express();

app.get('/search', (req, res) => {
  db.query("SELECT * FROM items WHERE name = '" + req.query.q + "'", (err, rows) => {
    res.send('<h1>Results for ' + req.query.q + '</h1>');
  });
});

app.get('/ping', (req, res) => {
  exec('ping -c 1 ' + req.query.host, (err, out) => res.send(out));
});

function render(el, html) {
  el.innerHTML = html;
}
`;

export const EXAMPLES = [
  { id: "plag", title: "Plagiarism case", desc: "A student solution, a renamed + reordered copy, and an AI-style rewrite.",
    files: [{ name: "alice_lab3.py", code: PY_HUMAN }, { name: "bob_lab3.py", code: PY_COPY }, { name: "carol_lab3.py", code: PY_AI }] },
  { id: "vuln", title: "Security audit", desc: "Classic injection, deserialisation and overflow bugs in four languages.",
    files: [{ name: "utils.py", code: PY_VULN }, { name: "UserDao.java", code: JAVA_VULN }, { name: "greet.c", code: C_VULN }, { name: "server.js", code: JS_VULN }] },
  { id: "ai", title: "AI vs human style", desc: "Same task written tersely by hand and verbosely by an assistant.",
    files: [{ name: "handwritten.py", code: PY_HUMAN }, { name: "assistant.py", code: PY_AI }] },
];
