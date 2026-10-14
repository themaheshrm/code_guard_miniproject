export const LANGS = { python: "python", java: "java", c: "c", cpp: "cpp", javascript: "javascript" };
const EXT = { py: "python", java: "java", c: "c", h: "c", cc: "cpp", cpp: "cpp", hpp: "cpp", js: "javascript", mjs: "javascript", jsx: "javascript" };

export const langOf = (name) => EXT[(name.split(".").pop() || "").toLowerCase()] || "python";
export const pct = (x) => (x == null ? "–" : `${Math.round(x * 100)}%`);

export const EXAMPLE = [
  { name: "alice_collatz.py", code: `import math\n\ndef circle_area(r):\n    # area of a circle\n    total = math.pi * r * r\n    return round(total, 2)\n\ndef collatz(n):\n    steps = 0\n    while n != 1:\n        if n % 2 == 0:\n            n //= 2\n        else:\n            n = 3 * n + 1\n        steps += 1\n    return steps\n\ndef fib(n):\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n` },
  { name: "bob_collatz.py", code: `import math\n\ndef fibonacci(count):\n    x, y = 0, 1\n    for _ in range(count):\n        x, y = y, x + y\n    return x\n\ndef collatz_len(num):\n    cnt = 0\n    unused = 5\n    while num != 1:\n        if num % 2 == 0:\n            num //= 2\n        else:\n            num = 3 * num + 1\n        cnt += 1\n    return cnt\n\ndef circle(radius):\n    t = math.pi * radius * radius\n    return round(t, 2)\n` },
  { name: "carol_utils.py", code: `import os, pickle, hashlib\n\ndef run(user_input):\n    os.system("ls " + user_input)\n    return hashlib.md5(user_input.encode()).hexdigest()\n\ndef load(blob):\n    return pickle.loads(blob)\n\ndef is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n ** 0.5) + 1):\n        if n % i == 0:\n            return False\n    return True\n` },
];

/** Pairs involving \`name\` (optionally restricted to one selected pair). */
export function pairsFor(report, name, selected) {
  const pairs = report?.plagiarism?.pairs || [];
  if (selected) return pairs.filter((p) => p.a === selected[0] && p.b === selected[1]).filter((p) => p.a === name || p.b === name);
  return pairs.filter((p) => p.flagged && (p.a === name || p.b === name));
}
