/**
 * A text as it is compared: lower case, without diacritics (the old cedilla letters too) and without dots or
 * other signs, so "brutaria" finds "Brutăria" and "srl" finds "S.R.L.".
 */
export function plain(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .replace(/\s+/g, ' ')
    .trim()
}

/** A CUI as it is compared: its digits, whether it is written with "RO" or not. */
export const digitsOf = (cui: string) => plain(cui).replace(/^ro\s*(?=\d)/, '')

/** The words typed in a search field, as they are compared. "RO 12345674" is one CUI, not the word "ro" and a number. */
export function searchWords(typed: string): string[] {
  return plain(typed).replace(/\bro (?=\d)/g, 'ro').split(' ').filter(Boolean)
}

/** Whether every word is in one of the texts, or in one of the CUIs. */
export function wordsFound(words: string[], texts: (string | null)[], cuis: (string | null)[]): boolean {
  const plainTexts = texts.filter((text): text is string => Boolean(text)).map(plain)
  const cuiDigits = cuis.filter((cui): cui is string => Boolean(cui)).map(digitsOf)
  return words.every((word) => plainTexts.some((text) => text.includes(word)) || cuiDigits.some((cui) => cui.includes(digitsOf(word))))
}
