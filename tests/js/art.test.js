// Las ilustraciones son funciones color → SVG; solo deben interpolar el color recibido.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const src = fs.readFileSync(path.join(__dirname, "../../src/radar/web/static/art.js"), "utf8");
const ctx = { window: {} };
vm.createContext(ctx);
vm.runInContext(src, ctx);
const ART = ctx.window.RADAR_ART;

test("existen las ilustraciones del contrato", () => {
  for (const k of ["vr", "robot", "wheel", "printer", "spool", "minipc", "hdd", "ssd", "ram", "cpu", "gpu", "laptop", "monitor", "phone", "headphones", "motherboard", "pc", "server", "smarthome"])
    assert.equal(typeof ART[k], "function", k);
});

test("cada ilustración devuelve un SVG válido, usa el color y no inyecta nada más", () => {
  for (const k of Object.keys(ART)) {
    const a = ART[k]("#123abc"), b = ART[k]("#fedcba");
    assert.match(a, /^<svg viewBox="0 0 300 150" aria-hidden="true">[\s\S]*<\/svg>$/, k);
    assert.ok(a.includes("#123abc"), k + " no usa el color");
    assert.equal(a.replaceAll("#123abc", "#fedcba"), b, k + " depende de algo más que el color");
    assert.ok(!/<script|on\w+=|javascript:|undefined|NaN/i.test(a), k);
    assert.equal((a.match(/<svg/g) || []).length, 1, k);
  }
});
