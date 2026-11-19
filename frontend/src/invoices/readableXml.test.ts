import { describe, expect, it } from 'vitest'
import { readableXml } from './readableXml'

// Made up, written the way some suppliers send it: the declaration, a tab, then all on one line.
const NAMESPACES =
  'xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2" ' +
  'xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2" ' +
  'xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"'
const ONE_LINE =
  '<?xml version="1.0" encoding="UTF-8"?>\n\t' +
  `<Invoice ${NAMESPACES}>` +
  '<cbc:ID>EX-0001</cbc:ID>' +
  '<cbc:IssueDate>2026-11-02</cbc:IssueDate>' +
  '<cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>Exemplu Furnizor SRL</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>' +
  '<cac:InvoiceLine><cbc:ID>1</cbc:ID>' +
  '<cbc:InvoicedQuantity unitCode="H87">2</cbc:InvoicedQuantity>' +
  '<cac:Item><cbc:Description>Hârtie A4  80 g, cutie de 5 topuri</cbc:Description><cbc:Name>Hârtie A4</cbc:Name></cac:Item>' +
  '</cac:InvoiceLine>' +
  '</Invoice>'

describe('an XML file made readable', () => {
  it('puts each element on its own line, nested ones indented, attributes and namespaces kept', () => {
    expect(readableXml(ONE_LINE)).toBe(
      [
        '<?xml version="1.0" encoding="UTF-8"?>',
        `<Invoice ${NAMESPACES}>`,
        '  <cbc:ID>EX-0001</cbc:ID>',
        '  <cbc:IssueDate>2026-11-02</cbc:IssueDate>',
        '  <cac:AccountingSupplierParty>',
        '    <cac:Party>',
        '      <cac:PartyName>',
        '        <cbc:Name>Exemplu Furnizor SRL</cbc:Name>',
        '      </cac:PartyName>',
        '    </cac:Party>',
        '  </cac:AccountingSupplierParty>',
        '  <cac:InvoiceLine>',
        '    <cbc:ID>1</cbc:ID>',
        '    <cbc:InvoicedQuantity unitCode="H87">2</cbc:InvoicedQuantity>',
        '    <cac:Item>',
        '      <cbc:Description>Hârtie A4  80 g, cutie de 5 topuri</cbc:Description>',
        '      <cbc:Name>Hârtie A4</cbc:Name>',
        '    </cac:Item>',
        '  </cac:InvoiceLine>',
        '</Invoice>',
      ].join('\n'),
    )
  })

  it('leaves the text inside an element exactly as it is', () => {
    const texts = [
      '<cbc:Note>Două  spații și   trei</cbc:Note>',
      '<cbc:Note>  la început și la sfârșit  </cbc:Note>',
      '<cbc:Note>   </cbc:Note>',
      '<cbc:Note>pe două\n    rânduri</cbc:Note>',
      '<cbc:Note>Exemplu &amp; Fiul &#x219; &lt;SRL&gt;</cbc:Note>',
      '<cbc:Note><![CDATA[  <nu este>  un element ]]></cbc:Note>',
    ]
    const shown = readableXml(`<Invoice ${NAMESPACES}>${texts.join('')}</Invoice>`)

    expect(shown.split('\n').slice(1, -1).join('\n')).toBe(texts.map((text) => `  ${text}`).join('\n'))
  })

  it('keeps an element whose text and elements are mixed as it is, since spaces there would change its text', () => {
    const mixed = '<cbc:Note>Plata <b>în 30 de zile</b> de la livrare</cbc:Note>'

    expect(readableXml(`<Invoice>${mixed}</Invoice>`)).toBe(`<Invoice>\n  ${mixed}\n</Invoice>`)
  })

  it('keeps an element that asks for its spaces to be kept as it is', () => {
    const kept = '<cac:Item xml:space="preserve"> <cbc:Name>Hârtie</cbc:Name> </cac:Item>'

    expect(readableXml(`<Invoice>${kept}</Invoice>`)).toBe(`<Invoice>\n  ${kept}\n</Invoice>`)
  })

  it('does not change a file that is already indented', () => {
    const indented = readableXml(ONE_LINE)

    expect(readableXml(indented)).toBe(indented)
  })

  it('re-indents a file indented badly', () => {
    const badly = '<Invoice>\n\t\t<cac:Item>\n<cbc:Name>Hârtie</cbc:Name>\n      </cac:Item>\r\n</Invoice>\n'

    expect(readableXml(badly)).toBe('<Invoice>\n  <cac:Item>\n    <cbc:Name>Hârtie</cbc:Name>\n  </cac:Item>\n</Invoice>')
  })

  it('keeps empty elements, comments and a ">" inside an attribute', () => {
    const shown = readableXml('<Invoice><!-- un comentariu --><cbc:Note/><cbc:Note></cbc:Note><cbc:ID schemeName="a>b">1</cbc:ID></Invoice>')

    expect(shown).toBe(
      ['<Invoice>', '  <!-- un comentariu -->', '  <cbc:Note/>', '  <cbc:Note></cbc:Note>', '  <cbc:ID schemeName="a>b">1</cbc:ID>', '</Invoice>'].join('\n'),
    )
  })

  it('shows a file that cannot be read as XML as it came', () => {
    const broken = [
      '<Invoice><cbc:ID>1</cbc:ID>',
      '<Invoice><cbc:ID>1</cbc:Name></Invoice>',
      '<Invoice><cbc:ID>1</cbc:ID></Invoice><Invoice></Invoice>',
      '<Invoice><cbc:ID x="1>1</cbc:ID></Invoice>',
      '<Invoice><!-- fără sfârșit </Invoice>',
      'text înainte <Invoice></Invoice>',
      '<Invoice></Invoice> text după',
      '</Invoice>',
      '< Invoice></Invoice>',
      'nu este XML',
      '',
    ]

    for (const xml of broken) expect(readableXml(xml)).toBe(xml)
  })
})
