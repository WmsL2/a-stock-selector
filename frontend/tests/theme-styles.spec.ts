import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('shared dark table theme', () => {
  it('keeps hover and current rows on the dark surface-hover token', () => {
    const css = readFileSync(resolve(__dirname, '../src/assets/main.css'), 'utf8')
    const compact = css.replace(/\s/g, '')
    expect(compact).toContain('--el-table-row-hover-bg-color:var(--surface-hover)')
    expect(compact).toContain('--el-table-current-row-bg-color:var(--surface-hover)')
  })
})
