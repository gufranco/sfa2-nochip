; Street Fighter Zero 2 (Japan), S-DD1 bypass.
;
; Same transform as the USA build, at the Japanese ROM's addresses. The engine
; is the same: sdd1sites.py finds seven writers of $4801 in this ROM too, and
; the bytes around each are identical to their USA counterparts, so the hooks
; and the shared routine apply unchanged.
;
; Three of the seven sit at the same file offset as in the USA ROM. Four moved,
; because the code ahead of them differs between the two builds:
;
;   USA $00:8482 -> JP $00:847E
;   USA $00:885A -> JP $00:8856
;   USA $00:8881 -> JP $00:887D
;   USA $00:F7BF -> JP $00:F7BF   unchanged
;   USA $25:BBD3 -> JP $25:C54A
;   USA $35:E002 -> JP $35:E002   unchanged
;   USA $35:E131 -> JP $35:E131   unchanged
;
; The routine cannot live at $35:CD84 here, because that address holds real
; data in this ROM rather than filler. The largest run of $FF in the same bank
; starts at file $01AD6F1 and is 783 bytes, so the routine goes at $35:D700,
; which leaves 768 bytes for a routine that assembles to 321.

lorom

!ROUTINE = $35D700              ; 783 bytes of $FF from file $01AD6F1

incsrc "sdd1-translate.asm"


; ---------------------------------------------------------------------------
; Hook sites. Each replaces the arming store and one of the two dummy stores
; that padded the chip's settle time, keeping the surviving dummy because at
; three sites it is a real store to direct page $00.
; ---------------------------------------------------------------------------

org $00847E                     ; VRAM queue at $0300,x
    jsl sdd1_ch0
    ldy $00
    nop

org $008856                     ; direct page source, carry live afterwards
    jsl sdd1_ch0
    sta $00
    nop

org $00887D                     ; continuation transfer, bank+1 and address 0
    jsl sdd1_ch0
    sta $00
    nop

org $00F7BF                     ; table-driven helper, channel offset in Y
    jsl sdd1_chy
    ldx $00
    nop

org $25C54A                     ; channel 1 into WRAM
    jsl sdd1_ch1
    sta $0000
    nop
    nop

org $35E002                     ; channel 7 into WRAM
    jsl sdd1_ch7
    ldx $00
    nop

org $35E131                     ; channel 0 into VRAM
    jsl sdd1_ch0
    ldx $00
    nop
