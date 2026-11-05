import assert from 'node:assert/strict'
import test from 'node:test'
import { readTheme } from '../../src/lib/appearance.ts'

test('Apparence : préférence locale, défaut système et valeur invalide', () => {
  assert.equal(readTheme({ getItem: () => 'dark' }, false), 'dark')
  assert.equal(readTheme({ getItem: () => 'light' }, true), 'light')
  assert.equal(readTheme({ getItem: () => null }, true), 'dark')
  assert.equal(readTheme({ getItem: () => '<script>' }, false), 'light')
})

test('Apparence : un stockage refusé ne bloque pas les conversations', () => {
  assert.equal(
    readTheme(
      {
        getItem() {
          throw new Error('denied')
        },
      },
      false,
    ),
    'light',
  )
})
