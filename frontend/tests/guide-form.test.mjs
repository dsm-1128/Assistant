import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'

import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { createServer } from 'vite'

let server
let html

before(async () => {
  server = await createServer({
    appType: 'custom',
    logLevel: 'silent',
    server: { middlewareMode: true },
  })
  const { default: GuideView } = await server.ssrLoadModule('/src/views/GuideView.vue')
  html = await renderToString(createSSRApp(GuideView))
})

after(async () => {
  await server?.close()
})

test('总预算使用 1 元步长以允许输入 999999', () => {
  assert.match(html, /<label>总预算<input[^>]*min="0"[^>]*step="1"[^>]*type="number"/)
})

test('币种选项显示中文说明且保持标准代码值', () => {
  const expectedOptions = [
    ['CNY', '人民币'],
    ['USD', '美元'],
    ['EUR', '欧元'],
    ['JPY', '日元'],
    ['HKD', '港币'],
  ]

  for (const [code, chineseName] of expectedOptions) {
    assert.match(
      html,
      new RegExp(`<option value="${code}"(?: [^>]*)?>${code}（${chineseName}）</option>`),
    )
  }
})
