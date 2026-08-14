lorom

!ROUTINE = $35CD84              ; 3196 bytes of $FF at file $01ACD84

incsrc "sdd1-translate.asm"

; ---------------------------------------------------------------------------
; Hook sites.
;
; Each site ends with the same shape: arm $4801, two dummy stores that gave the
; chip time to settle, then start the transfer with $420B. The arming store and
; one dummy are replaced by the JSL. The surviving dummy is re-encoded rather
; than dropped, because at three of the sites it is a real store to direct page
; $00 whose value some later read may depend on, and the routine preserves A, X
; and Y so re-encoding it reproduces the original effect exactly.
;
; Site addresses come from sdd1sites.py, which masks off the 2,565,930 bytes of
; known compressed data before scanning, so these seven are code and not chance
; byte sequences inside graphics.
; ---------------------------------------------------------------------------

org $008482                     ; VRAM queue at $0300,x. Original bytes:
    jsl sdd1_ch0                ;   8D 01 48  A4 00  A4 00
    ldy $00
    nop

org $00885A                     ; direct page $18/$1a source. Original bytes:
    jsl sdd1_ch0                ;   8D 01 48  85 00  85 00
    sta $00                     ; the following BCC needs the carry, which the
    nop                         ;   routine preserves through PHP/PLP

org $008881                     ; continuation transfer, bank+1 and address 0.
    jsl sdd1_ch0                ;   8D 01 48  85 00  85 00
    sta $00
    nop

org $00F7BF                     ; table-driven helper, channel offset in Y.
    jsl sdd1_chy                ;   8D 01 48  A6 00  A6 00
    ldx $00
    nop

org $25BBD3                     ; channel 1 into WRAM, parameters at $C8:F017.
    jsl sdd1_ch1                ;   8D 01 48  8D 00 00  8D 00 00
    sta $0000
    nop
    nop

org $35E002                     ; channel 7 into WRAM.
    jsl sdd1_ch7                ;   8D 01 48  A6 00  A6 00
    ldx $00
    nop

org $35E131                     ; channel 0 into VRAM.
    jsl sdd1_ch0                ;   8D 01 48  A6 00  A6 00
    ldx $00
    nop
