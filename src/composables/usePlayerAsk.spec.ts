import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { usePlayerAsk } from './usePlayerAsk'

const intents = (topic: string) => ({ 'char-wren': { topic } })

describe('usePlayerAsk', () => {
  it('clears the composer on a confirmed submission', async () => {
    const text = ref('What news from the mill?')
    const submit = usePlayerAsk(async () => true, text)
    await expect(submit(intents)).resolves.toBe(true)
    expect(text.value).toBe('')
  })

  it('a conflict preserves the unconfirmed question', async () => {
    const text = ref('What news from the mill?')
    const submit = usePlayerAsk(async () => false, text)
    await expect(submit(intents)).resolves.toBe(false)
    expect(text.value).toBe('What news from the mill?')
  })

  it('a duplicate reconciliation preserves the unconfirmed question', async () => {
    const text = ref('What news from the mill?')
    const advance = vi.fn(async () => false)
    const submit = usePlayerAsk(advance, text)
    await expect(submit(intents)).resolves.toBe(false)
    expect(advance).toHaveBeenCalledOnce()
    expect(text.value).toBe('What news from the mill?')
  })

  it('a delayed success preserves newer edits typed mid-flight', async () => {
    const text = ref('Older')
    let release!: (confirmed: boolean) => void
    const gate = new Promise<boolean>((res) => {
      release = res
    })
    const submit = usePlayerAsk(() => gate, text)
    const pending = submit(intents)
    // The player keeps typing while the beat commits.
    text.value = 'Newest'
    release(true)
    await expect(pending).resolves.toBe(true)
    expect(text.value).toBe('Newest')
  })

  it('blank text never files', async () => {
    const text = ref('   ')
    const advance = vi.fn(async () => true)
    const submit = usePlayerAsk(advance, text)
    await expect(submit(intents)).resolves.toBe(false)
    expect(advance).not.toHaveBeenCalled()
  })
})
