import { describe, expect, it } from 'vitest'

import { formatBytes } from '@/utils/format'

describe('formatBytes', () => {
  it.each([
    [0, '0 B'],
    [1024, '1.0 KB'],
    [1024 ** 2, '1.0 MB'],
    [1024 ** 3, '1.0 GB'],
  ])('formats %d bytes as %s', (value, expected) => {
    expect(formatBytes(value)).toBe(expected)
  })
})
