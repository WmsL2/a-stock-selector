import { describe, expect, it } from 'vitest'

import { createLatestRequestGuard } from '@/utils/latestRequestGuard'

describe('createLatestRequestGuard', () => {
  it('returns a current first token', () => {
    const guard = createLatestRequestGuard()
    expect(guard.isCurrent(guard.begin())).toBe(true)
  })

  it('invalidates an earlier token when a later request begins', () => {
    const guard = createLatestRequestGuard()
    const first = guard.begin()
    const second = guard.begin()
    expect(guard.isCurrent(first)).toBe(false)
    expect(guard.isCurrent(second)).toBe(true)
  })

  it('keeps independent guards isolated and isCurrent is non-mutating', () => {
    const first = createLatestRequestGuard()
    const second = createLatestRequestGuard()
    const token = first.begin()
    expect(first.isCurrent(token)).toBe(true)
    expect(first.isCurrent(token)).toBe(true)
    expect(second.isCurrent(token)).toBe(false)
  })
})
