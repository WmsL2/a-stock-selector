export interface LatestRequestGuard {
  begin(): number
  isCurrent(token: number): boolean
}

export function createLatestRequestGuard(): LatestRequestGuard {
  let generation = 0
  return {
    begin(): number {
      generation += 1
      return generation
    },
    isCurrent(token: number): boolean {
      return token === generation
    },
  }
}
