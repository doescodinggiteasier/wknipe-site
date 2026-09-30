// Unit tests for the AI-policy checker's robots.txt logic (RFC 9309) and domain validation.
// Run: node --experimental-strip-types scripts/check.test.mjs   (Node >= 22.6)
import assert from "node:assert/strict";
import { parseRobots, evaluate, normaliseDomain } from "../src/check.ts";

const ev = (txt, bot, path = "/") => evaluate(parseRobots(txt).groups, bot, path).status;

// Named group beats '*'; token match is case-insensitive
assert.equal(ev("User-agent: *\nDisallow: /\n\nUser-agent: gptbot\nAllow: /", "GPTBot"), "allowed");
assert.equal(ev("User-agent: *\nDisallow: /\n\nUser-agent: gptbot\nAllow: /", "ClaudeBot"), "blocked");
// Longest match wins; equal length -> allow
assert.equal(ev("User-agent: *\nDisallow: /\nAllow: /$", "X", "/"), "partial");
assert.equal(ev("User-agent: *\nDisallow: /a\nAllow: /a", "X", "/a"), "partial");
assert.equal(ev("User-agent: *\nDisallow: /a\nAllow: /a", "X", "/a") === "blocked", false);
// Empty Disallow means allow everything
assert.equal(ev("User-agent: GPTBot\nDisallow:", "GPTBot"), "allowed");
// Multiple user-agent lines share one group; groups naming the same bot are combined
assert.equal(ev("User-agent: GPTBot\nUser-agent: CCBot\nDisallow: /", "CCBot"), "blocked");
assert.equal(ev("User-agent: GPTBot\nDisallow: /private\n\nUser-agent: GPTBot\nDisallow: /", "GPTBot"), "blocked");
// A group ends when a user-agent line follows rules
assert.equal(ev("User-agent: A\nDisallow: /\nUser-agent: B\nAllow: /", "B"), "allowed");
// Wildcards and end anchors
assert.equal(ev("User-agent: *\nDisallow: /*.pdf$", "X", "/"), "partial");
assert.equal(ev("User-agent: *\nDisallow: /*.pdf$", "X", "/a.pdf"), "blocked");
// No matching group and no '*' -> allowed, via none
assert.equal(evaluate(parseRobots("User-agent: Foo\nDisallow: /").groups, "GPTBot").via, "none");
// Comments, CRLF, Content-Signal and License lines
const p = parseRobots("# hi\r\nUser-agent: *\r\nContent-Signal: search=yes, ai-train=no\r\nDisallow: /x # c\r\nLicense: https://e.com/l.xml\r\n");
assert.deepEqual(p.licenses, ["https://e.com/l.xml"]);
assert.equal(p.signals[0].value, "search=yes, ai-train=no");
assert.deepEqual(p.signals[0].agents, ["*"]);

// Domain validation: public names only
assert.equal(normaliseDomain("https://WWW.Example.org/path?q=1"), "www.example.org");
assert.equal(normaliseDomain("bbc.co.uk"), "bbc.co.uk");
for (const bad of ["localhost", "127.0.0.1", "http://10.0.0.1", "[::1]", "foo", "a.local", "x.internal", "example.com:8080",
                   "user@example.com", "http://user:pw@example.com", "exa mple.com", "", null, "a..b.com", "-a.com"]) {
  assert.equal(normaliseDomain(bad), null, `should reject ${bad}`);
}
console.log("check.test.mjs: all assertions passed");
