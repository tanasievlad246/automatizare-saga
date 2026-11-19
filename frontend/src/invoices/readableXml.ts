/** What the button over an XML file says, and what it says when the file could not be copied. */
export const COPY_XML = {
  button: 'Copiază XML-ul',
  copied: 'Copiat',
  refused: 'XML-ul nu a fost copiat.',
}

/**
 * An XML file laid out to be read: each element on its own line, the ones inside it indented.
 * Only the spaces and line breaks between elements change: what is inside an element, and the
 * tags themselves, stay exactly as they came. A file that cannot be read as XML comes back as it is.
 */
export function readableXml(xml: string): string {
  const top = parse(xml)
  if (!top) return xml
  return top.filter((node) => node.kind !== 'text').flatMap((node) => lines(xml, node, 0)).join('\n')
}

const INDENT = '  '
/** The spaces XML puts between elements, which say nothing. */
const ONLY_SPACES = /^[ \t\r\n]*$/
/** An element that asks for its spaces to be kept, as text is laid out in it. */
const KEEPS_SPACES = /\sxml:space\s*=\s*(["'])preserve\1/

type Element = { kind: 'element'; start: string; end: string; from: number; to: number; children: Node[] }
/** Text is also a CDATA section; "other" is a comment, a declaration or an instruction. */
type Node = Element | { kind: 'text' | 'other'; raw: string }

/** The nodes at the top of the file, or null when it is not XML: tags left open or crossed, one root. */
function parse(xml: string): Node[] | null {
  const top: Node[] = []
  const open: { name: string; element: Element }[] = []
  const add = (node: Node) => (open.at(-1)?.element.children ?? top).push(node)
  let at = xml.startsWith('﻿') ? 1 : 0
  while (at < xml.length) {
    const from = xml.indexOf('<', at)
    const textEnd = from === -1 ? xml.length : from
    if (textEnd > at) add({ kind: 'text', raw: xml.slice(at, textEnd) })
    if (from === -1) break
    const to = markupEnd(xml, from)
    if (to === -1) return null
    const raw = xml.slice(from, to)
    at = to
    if (raw.startsWith('<![CDATA[')) add({ kind: 'text', raw })
    else if (raw.startsWith('<!') || raw.startsWith('<?')) add({ kind: 'other', raw })
    else if (raw.startsWith('</')) {
      const closed = open.pop()
      if (!closed || closed.name !== raw.slice(2, -1).trim()) return null
      closed.element.end = raw
      closed.element.to = to
    } else {
      const name = /^<([^\s/<>"'=]+)/.exec(raw)?.[1]
      if (!name) return null
      const element: Element = { kind: 'element', start: raw, end: '', from, to, children: [] }
      add(element)
      if (!raw.endsWith('/>')) open.push({ name, element })
    }
  }
  const roots = top.filter((node) => node.kind === 'element')
  const onlySpacesOutside = top.every((node) => node.kind !== 'text' || ONLY_SPACES.test(node.raw))
  if (open.length > 0 || roots.length !== 1 || !onlySpacesOutside) return null
  return top
}

/** Where the tag, comment or declaration starting at `from` ends, or -1 when it does not. */
function markupEnd(xml: string, from: number): number {
  for (const [opening, closing] of [['<!--', '-->'], ['<![CDATA[', ']]>'], ['<?', '?>']]) {
    if (!xml.startsWith(opening, from)) continue
    const found = xml.indexOf(closing, from + opening.length)
    return found === -1 ? -1 : found + closing.length
  }
  // A tag, or a declaration such as <!DOCTYPE …>: up to the first ">" outside quotes and, in a declaration, [ ].
  const declaration = xml.startsWith('<!', from)
  let quote = ''
  let brackets = 0
  for (let at = from + 1; at < xml.length; at++) {
    const char = xml[at]
    if (quote) {
      if (char === quote) quote = ''
    } else if (char === '"' || char === "'") quote = char
    else if (declaration && char === '[') brackets++
    else if (declaration && char === ']') brackets--
    else if (brackets === 0 && char === '<') return -1
    else if (brackets === 0 && char === '>') return at + 1
  }
  return -1
}

/** One node's lines at its depth. An element holding text is kept on its line exactly as it came. */
function lines(xml: string, node: Node, depth: number): string[] {
  const indent = INDENT.repeat(depth)
  if (node.kind !== 'element') return [indent + node.raw]
  const { children } = node
  // Spaces may be added only where an element holds nothing but other elements (and spaces).
  const holdsOnlyElements =
    children.some((child) => child.kind !== 'text') &&
    children.every((child) => child.kind !== 'text' || ONLY_SPACES.test(child.raw)) &&
    !KEEPS_SPACES.test(node.start)
  if (!holdsOnlyElements) return [indent + xml.slice(node.from, node.to)]
  return [
    indent + node.start,
    ...children.filter((child) => child.kind !== 'text').flatMap((child) => lines(xml, child, depth + 1)),
    indent + node.end,
  ]
}
