/** Test the TypeScript view-model behaviour without a package download. */
import assert from 'node:assert/strict'
import test from 'node:test'

import { greeting } from './greeting.ts'

test('the React view model uses the requested French greeting', () => {
  /** Verify the source logic before and after the OpenHands correction. */
  assert.equal(greeting('Léa'), 'Bonjour Léa')
})
