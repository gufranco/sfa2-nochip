; Street Fighter Alpha 2 / Zero 2, the pre-fight table by DMA.
;
; ---------------------------------------------------------------------------
; What this replaces
; ---------------------------------------------------------------------------
;
; Before every fight the game builds a 24,704 byte table in work RAM at
; $7E:9440. The builder is at $C0:B606 in the USA ROM and $C0:B60B in the
; Japanese one, found by the 26 byte signature of its opening constants rather
; than by address, and it is called from two places in each region.
;
; The builder takes no input. It starts from a fixed 32 bit value, subtracts a
; fixed step 64 times writing the high word of each result, then advances the
; start and shrinks the step, 193 times over:
;
;   C0:B60C  lda #$7a00 / #$004b     the running value, $004B7A00
;   C0:B616  lda #$1820 / #$0001     the step, $00011820
;   C0:B620  lda #$00c1              193 rows
;   C0:B62D  lda #$0040              64 columns
;   C0:B634  sta $7e9440,x           the high word of the running value
;   C0:B64E  adc #$8c10              the start advances by this each row
;   C0:B65D  sbc #$02eb              and the step shrinks by this
;
; Nothing in it reads the stage, the characters or anything else, so the table
; is a constant. prefight.py reproduces it in Python and the result was
; compared against work RAM dumped from the running console after two different
; matchups: 24,704 of 24,704 bytes identical both times.
;
; Building it costs about thirteen frames of a load that the player waits
; through. Storing the finished table and moving it with one DMA replaces that
; with a transfer of roughly half a frame, during which the processor is
; halted rather than working.
;
; ---------------------------------------------------------------------------
; Why this is a chip-free only change
; ---------------------------------------------------------------------------
;
; The table needs 24,704 bytes. The largest run of filler anywhere in either
; retail cartridge is 3,210 bytes, and all the filler in the USA ROM together
; comes to 14,826, so it does not fit in the 4 MB form at any address. The
; 96 Mbit image has room: its data banks carry 390,319 spare bytes on the USA
; build and 443,287 on the Japanese one after every decompressed stream is
; placed, so rombuild.py reserves the table a fixed home at $5F:0000 and the
; allocator is never offered that span.
;
; The 4 MB cartridge therefore keeps the stock builder and the thirteen frames.
; That is the one place in this project where the two cartridge forms differ in
; behaviour rather than only in layout, and it is deliberate: the alternative
; is giving up a saving the larger image can afford.
;
; ---------------------------------------------------------------------------
; The transfer
; ---------------------------------------------------------------------------
;
; Entry:  called by jsl from either of the builder's two call sites, with the
;         register widths and the data bank whatever the caller happened to
;         hold, which is why every hardware store below is long addressed
; Exit:   rtl, with the processor status restored by plp, so the caller sees
;         the same flags and the same interrupt state it had. A is clobbered,
;         which the stock builder also does, and both call sites discard it
;
; The interrupt disable spans the register setup rather than the transfer. A
; frame interrupt cannot land inside the transfer, because the processor is
; halted for its whole duration, but it can land between programming channel
; zero and starting it, and the frame handler drives channel zero itself.
;
; asar is told the plain LoROM mapping, under which file offset F is bank
; F >> 15 at address $8000 + (F & $7FFF). The routine sits in the run of $FF
; that fills file $07F593 to the end of that bank, 2,671 bytes, free in both
; regional ROMs. The game reaches it through the window as $C7:F593, which is
; the address prefight.py writes into the two call sites.
; ---------------------------------------------------------------------------

lorom

!TABLE_SOURCE = $5F0000         ; where rombuild.py reserves the finished table
!TABLE_LENGTH = $6080           ; 193 rows of 64 words
!TABLE_TARGET = $9440           ; work RAM $7E:9440

!WRAM_ADDRESS_LOW  = $002181    ; work RAM address for the $2180 port
!WRAM_ADDRESS_BANK = $002183    ; bit 0 chooses $7E or $7F
!DMA_PARAMETERS    = $004300    ; one byte to one register, incrementing
!DMA_B_BUS         = $004301    ; the $21xx register the transfer feeds
!DMA_SOURCE        = $004302    ; source address, then bank at $004304
!DMA_SOURCE_BANK   = $004304
!DMA_LENGTH        = $004305
!DMA_ENABLE        = $00420B

!B_BUS_WRAM  = $80              ; $2180, the work RAM data port
!CHANNEL_ZERO = $01

org $0FF593

prefight_table:
    php
    sei
    rep #$30
    lda.w #!TABLE_TARGET
    sta.l !WRAM_ADDRESS_LOW      ; a 16 bit store fills $2181 and $2182
    sep #$20
    lda #$00
    sta.l !WRAM_ADDRESS_BANK     ; $7E rather than $7F
    sta.l !DMA_PARAMETERS
    lda #!B_BUS_WRAM
    sta.l !DMA_B_BUS
    lda #!TABLE_SOURCE>>16
    sta.l !DMA_SOURCE_BANK
    rep #$20
    lda.w #!TABLE_SOURCE&$FFFF
    sta.l !DMA_SOURCE
    lda.w #!TABLE_LENGTH
    sta.l !DMA_LENGTH
    sep #$20
    lda #!CHANNEL_ZERO
    sta.l !DMA_ENABLE            ; the processor halts here until it is done
    plp
    rtl

warnpc $0FF700
