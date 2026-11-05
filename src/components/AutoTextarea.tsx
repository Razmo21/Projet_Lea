import { useLayoutEffect, useRef } from 'react'
import type { Ref, TextareaHTMLAttributes } from 'react'

type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  ref?: Ref<HTMLTextAreaElement>
}

// La saisie suit le texte sur une à quatre lignes, puis défile sans grandir davantage.
export default function AutoTextarea({ ref: forwardedRef, ...props }: Props) {
  const element = useRef<HTMLTextAreaElement | null>(null)

  useLayoutEffect(() => {
    const input = element.current
    if (!input) return

    // Mesure aussi les lignes repliées, en tenant compte de la police et des espacements.
    function resize() {
      if (!input || !input.getClientRects().length) return
      const style = getComputedStyle(input)
      const lineHeight = parseFloat(style.lineHeight)
      const padding =
        parseFloat(style.paddingTop) + parseFloat(style.paddingBottom)
      const borders =
        parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth)
      const maximum = Math.ceil(4 * lineHeight + padding + borders)

      // Repartir de la hauteur native permet de rétrécir après un effacement.
      input.style.height = 'auto'
      input.style.overflowY = 'hidden'
      const contentHeight = input.value
        ? input.scrollHeight + borders
        : Math.ceil(lineHeight + padding + borders)
      input.style.height = `${Math.min(contentHeight, maximum)}px`
      input.style.overflowY = contentHeight > maximum ? 'auto' : 'hidden'
    }
    resize()
    // Ne surveille que les changements de largeur, pour éviter une boucle sur la hauteur.
    let width = input.clientWidth
    const observer = new ResizeObserver(() => {
      if (input.clientWidth !== width) {
        width = input.clientWidth
        resize()
      }
    })
    observer.observe(input)
    return () => observer.disconnect()
  }, [props.value])

  return (
    <textarea
      {...props}
      ref={(node) => {
        element.current = node
        if (typeof forwardedRef === 'function') forwardedRef(node)
        else if (forwardedRef) forwardedRef.current = node
      }}
    />
  )
}
