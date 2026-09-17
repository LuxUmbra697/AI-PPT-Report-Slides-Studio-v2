import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const files = process.argv.slice(2)

for (const name of files.length ? files : ['index.html']) {
  const html = readFileSync(path.resolve(root, name), 'utf8')
  const links = [...html.matchAll(/<link\b[^>]*>/gi)]
    .map(([tag]) => Object.fromEntries(
      [...tag.matchAll(/([\w-]+)="([^"]*)"/g)].map(([, key, value]) => [key, value]),
    ))
    .filter((attrs) => (attrs.rel || '').split(/\s+/).includes('icon'))
  assert.equal(links.length, 1, `${name}: exactly one explicit tab icon is required`)
  assert.equal(links[0].type, 'image/svg+xml')
  assert.ok(links[0].href.startsWith('data:image/svg+xml,'), `${name}: no shared-origin icon request`)
  const svg = decodeURIComponent(links[0].href.slice('data:image/svg+xml,'.length))
  assert.match(svg, /^<svg\s+xmlns="http:\/\/www\.w3\.org\/2000\/svg"\s+viewBox="0 0 16 16"><\/svg>$/)
  assert.match(html, /<title>Slide Report Studio<\/title>/)
  assert.match(html, /<div id="root"><\/div>/)
  assert.match(html, /<script\b[^>]*type="module"/)
  console.log(`PASS ${name}: transparent tab icon; app entry and title preserved`)
}
