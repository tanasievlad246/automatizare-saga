import { describe, expect, it } from 'vitest'
import type { Where } from './types'
import { opensWindowsHere, pathOnThisPC, pcKind } from './where'

const onTheNas: Where = {
  mode: 'network',
  on_this_computer: false,
  saga_folder: '/saga',
  saga_folder_windows: '\\\\192.168.1.50\\AutoSaga-SAGA',
  saga_folder_mac: '/Volumes/AutoSaga-SAGA',
}
const FILE = '/saga/Alfa Construct SRL - 12345674/F_12345674_FV-1.xml'

describe('pathOnThisPC', () => {
  it('gives a Windows PC the path through the shared folder', () => {
    expect(pathOnThisPC(FILE, onTheNas, 'windows')).toBe(
      '\\\\192.168.1.50\\AutoSaga-SAGA\\Alfa Construct SRL - 12345674\\F_12345674_FV-1.xml',
    )
  })

  it('gives a Mac the path where the share is mounted', () => {
    expect(pathOnThisPC(FILE, onTheNas, 'mac')).toBe('/Volumes/AutoSaga-SAGA/Alfa Construct SRL - 12345674/F_12345674_FV-1.xml')
  })

  it('gives the folder itself, and a share written with a separator at its end', () => {
    expect(pathOnThisPC('/saga', onTheNas, 'windows')).toBe('\\\\192.168.1.50\\AutoSaga-SAGA')
    expect(pathOnThisPC(FILE, { ...onTheNas, saga_folder_mac: '/Volumes/AutoSaga-SAGA/' }, 'mac')).toBe(
      '/Volumes/AutoSaga-SAGA/Alfa Construct SRL - 12345674/F_12345674_FV-1.xml',
    )
  })

  it('keeps a mapped drive whole: S: alone would be the current folder of S, not its root', () => {
    const mapped: Where = { ...onTheNas, saga_folder_windows: 'S:\\' }

    expect(pathOnThisPC('/saga', mapped, 'windows')).toBe('S:\\')
    expect(pathOnThisPC(FILE, mapped, 'windows')).toBe('S:\\Alfa Construct SRL - 12345674\\F_12345674_FV-1.xml')
  })

  it('turns a program on Windows into the Mac form too', () => {
    const onAWindowsPc: Where = { ...onTheNas, saga_folder: 'C:\\SAGA Import', saga_folder_mac: '/Volumes/SAGA Import' }

    expect(pathOnThisPC('C:\\SAGA Import\\Beta SRL - 456\\F.xml', onAWindowsPc, 'mac')).toBe('/Volumes/SAGA Import/Beta SRL - 456/F.xml')
  })

  it('leaves alone what is not in the folder for SAGA', () => {
    expect(pathOnThisPC('/saga-other/F.xml', onTheNas, 'windows')).toBe('/saga-other/F.xml')
    expect(pathOnThisPC('/data/saga-archive/1/F.xml', onTheNas, 'windows')).toBe('/data/saga-archive/1/F.xml')
  })

  it('leaves the path as it is where nothing would change it', () => {
    expect(pathOnThisPC(FILE, { ...onTheNas, saga_folder_windows: null }, 'windows')).toBe(FILE)
    expect(pathOnThisPC(FILE, onTheNas, 'other')).toBe(FILE)
    expect(pathOnThisPC(FILE, { ...onTheNas, on_this_computer: true }, 'windows')).toBe(FILE)
    expect(pathOnThisPC(FILE, { ...onTheNas, mode: 'local' }, 'windows')).toBe(FILE)
    expect(pathOnThisPC(FILE, undefined, 'windows')).toBe(FILE)
  })
})

describe('pcKind', () => {
  it('tells Windows from a Mac by the browser', () => {
    expect(pcKind('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0')).toBe('windows')
    expect(pcKind('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15')).toBe('mac')
    expect(pcKind('Mozilla/5.0 (X11; Linux x86_64) Firefox/140.0')).toBe('other')
  })
})

describe('opensWindowsHere', () => {
  it('is so on the computer that runs the program, and until the program has said', () => {
    expect(opensWindowsHere({ ...onTheNas, on_this_computer: true })).toBe(true)
    expect(opensWindowsHere(undefined)).toBe(true)
    expect(opensWindowsHere(onTheNas)).toBe(false)
  })
})
