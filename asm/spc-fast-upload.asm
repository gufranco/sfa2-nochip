; Street Fighter Alpha 2 / Zero 2, fast sample upload.
;
; ---------------------------------------------------------------------------
; The problem
; ---------------------------------------------------------------------------
;
; Every fight is preceded by a pause of about three seconds. Measured on the
; retail USA ROM under snes9x 1.63 with the APU write ports
; instrumented, one pre-fight burst is 184 frames long and moves 47,915 bytes
; into SPC700 RAM. That is 15.3 KB/s, or 260 bytes per frame against 262
; scanlines: one byte per scanline.
;
; The receiving half is NOT the S-SMP IPL boot ROM. Sampling the SPC700
; program counter on every APU port write gives about 3,600 hits inside
; $FFC0-$FFFF against roughly 180,000 hits in RAM at $0EBD-$0F26. That RAM
; code is the game's own sound driver, which re-implements the IPL transfer
; protocol, and it is uploaded from ROM, so it can be changed.
;
; The driver is the bottleneck, not the 65816. Its per-byte loop was:
;
;   0EC9  push y           4
;   0ECA  mov y,$00f4      4    read the counter port
;   0ECD  cmp y,$00f4      4    read it again
;   0ED0  bne $0eca        2    and loop while the two reads disagree
;   0ED2  mov $0e7,y       4    stash the value
;   0ED4  pop y            4    recover the store index
;   0ED5  cmp y,$0e7       3    has the CPU posted our index?
;   0ED7  bne $0eed        2    no: block finished or a new block starts
;   0ED9  mov a,$00f5      4    one data byte
;   0EDC  cmp a,$00f5      4    read it again
;   0EDF  bne $0ed9        2    and loop while the two reads disagree
;   0EE1  mov $00f4,y      5    echo the counter back
;   0EE4  mov ($014)+y,a   7    store
;   0EE6  inc y            2
;   0EE7  bne $0ec9        4
;
; That is about 55 cycles. At 1.024 MHz it is roughly 54 us of the 65 us the
; measurement gives per byte, so the 65816 spends nearly all of the pause
; waiting on the SPC700.
;
; ---------------------------------------------------------------------------
; The fix
; ---------------------------------------------------------------------------
;
; The S-SMP's own IPL boot ROM performs the same job in about half the cycles,
; and its listing is the reference for what this loop needs to be:
;
;   ffda  cmp y,$f4        compare the store index against the counter port
;   ffdc  bne $ffe9
;   ffde  mov a,$f5        one data byte
;   ffe0  mov $f4,y        echo the counter back
;   ffe2  mov ($00)+y,a    store
;   ffe4  inc y
;   ffe5  bne $ffda
;
; Three things the driver does are pure overhead. It pushes and pops Y around
; the port read only because it loads the counter into Y instead of comparing
; against it in place, and cmp y,dp does that comparison directly, needing no
; scratch byte and no stack traffic. It reads each port twice and discards
; disagreeing pairs, but an APU port is a single latched byte and a read of it
; is atomic, so the second read can never differ. And it addresses the ports
; absolutely at four cycles each when the driver's own direct page is zero,
; which the surrounding code proves by reaching $0014 and $00E7 as direct page,
; so the cheaper direct page form is available.
;
; Removing all three gives roughly 25 cycles per byte against 55.
;
; The wire protocol is deliberately left alone: still one data byte per
; handshake through $F5, still a counter stepping by one, still the same block
; header. That matters because the game does not have one uploader, it has
; seven, at $C7:0252, $C7:02E2, $C7:0366, $C7:03F3, $C7:0412, $C7:0431 and
; $C7:04A9, and the one at $C7:0252 also drives the IPL boot ROM, which is mask
; ROM inside the S-SMP and cannot be changed. Anything that alters the protocol
; must change all seven and would still deadlock the boot upload. Making the
; receiver faster instead leaves every one of them working untouched.
;
; A first attempt did change the protocol, carrying a second data byte in the
; idle $F6 port so each handshake moved two bytes. It measured 602 bytes per
; frame against 260, but it converted only two of the seven uploaders, and the
; remaining five deadlocked against the new receiver: the CPU sat at $C7:035E
; for 484 frames of a 1,200 frame run and the screen never came up. That is why
; this patch changes the receiver's speed rather than the protocol.
;
; ---------------------------------------------------------------------------
; The blank gate
; ---------------------------------------------------------------------------
;
; Each 65816 upload loop also gates every byte on $4212, waiting for H-blank or
; V-blank before posting it. The echo handshake is the real synchronisation and
; the gate only throttles the transfer; with the stock driver, removing it at
; all seventeen sites measured 3.07 s down to 2.40 s on its own. The gates are
; replaced by nops, which keeps every instruction after them at its original
; address so no branch target in the sound bank moves.
;
; ---------------------------------------------------------------------------
; Addresses and how they were established
; ---------------------------------------------------------------------------
;
; The sound driver is byte-identical in both regional ROMs. Searching for the
; 32-byte signature of the receive loop taken from a live APU RAM dump finds
; exactly one hit, at file offset $072B13, in sfa2-usa-final.sfc and in
; sfz2-jp-final.sfc alike. That anchors the driver image: SPC address A sits at
; file offset $071C56 + A, confirmed by comparing live RAM against the ROM at
; $0EBD, $0EC9, $0EFF and $0F26.
;
; The seventeen blank gates were found by searching bank $C7 for the eight byte
; sequence AF 12 42 00 29 C0 F0 F8, which is lda.l $004212 / and #$c0 / beq
; back to the lda. Every hit is inside an upload loop or a block header
; handshake.
;
; asar is told the plain LoROM mapping, under which file offset F is bank
; F >> 15 at address $8000 + (F & $7FFF). The game runs this code from bank $C7
; through the S-DD1 memory controller window, but nothing below transfers
; control across a bank, so the bank it executes from does not matter.
;
;   SPC  $0EC9    ->  file $072B1F  ->  $0E:AB1F
;   CPU  $C7:0222 ->  file $070222  ->  $0E:8222, the first blank gate

lorom

!SPC_LOOP  = $0EAB1F             ; SPC $0EC9, the per-byte receive loop
!BANK_BASE = $0E8000             ; file $070000, the start of sound bank $C7

!PORT_COUNTER = $f4              ; APU port 0 as direct page, driver DP is zero
!PORT_DATA    = $f5              ; APU port 1, the only port carrying payload
!DEST_LOW     = $14              ; driver's destination pointer, low byte
!DEST_PAGE    = $15              ; driver's destination pointer, page byte

!PORT_COUNTER_L = $002140        ; APU port 0 seen from the 65816
!PORT_DATA0     = $002141        ; APU port 1, first data byte
!PORT_DATA1     = $002142        ; APU port 2, second data byte
!RESUME         = $04B5          ; CPU $C7:04B5, stock end-of-block path


; ---------------------------------------------------------------------------
; SPC700 side: the same protocol, at IPL speed.
;
; Entry:  Y = store index, which is also the counter value the CPU must post
;         $14/$15 = destination pointer, set by the block header at $0EFF
; Exit:   falls through to $0EED when the posted counter stops matching Y,
;         the driver's existing end-of-block and new-block path, reached with
;         the flags of the same comparison that path already expects
;
; The data port is read before the counter is echoed. The echo is what releases
; the CPU to overwrite that port, so reading first is what keeps the byte valid.
; ---------------------------------------------------------------------------

arch spc700
org !SPC_LOOP

spc_receive_byte:
    cmp   y,!PORT_COUNTER        ; has the CPU posted exactly our index?
    bne   spc_block_edge         ; no: block finished, or a new block begins
    mov   a,!PORT_DATA           ; the data byte, valid until we echo
    mov   !PORT_COUNTER,y        ; echo the counter, releasing the CPU
    mov   (!DEST_LOW)+y,a        ; store at the current index
    inc   y
    bne   spc_receive_byte
    inc   !DEST_PAGE             ; index wrapped, carry into the page byte
    bra   spc_receive_byte

    nop                          ; pad to the stock routine's length so the
    nop                          ; end-of-block path below keeps its address
    nop                          ; and every branch into it stays correct
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop

spc_block_edge:
    ; $0EED onwards is stock driver code and is deliberately left untouched


; ---------------------------------------------------------------------------
; 65816 side: retire the blank gate at all seventeen sites.
;
; Each site is lda.l $004212 / and #$c0 / beq back to the lda, eight bytes that
; stall until the PPU reports H-blank or V-blank. Replacing them with nops
; keeps the following instruction at its original address.
; ---------------------------------------------------------------------------

arch 65816

macro blank_gate(offset)
org !BANK_BASE+<offset>
    nop                          ; lda.l $004212
    nop
    nop
    nop
    nop                          ; and #$c0
    nop
    nop                          ; beq back to the read
    nop
endmacro

%blank_gate($0222)               ; block header,  uploader $C7:01F9
%blank_gate($0241)               ; byte loop,     uploader $C7:01F9
%blank_gate($025F)               ; end of block,  uploader $C7:01F9
%blank_gate($02B2)
%blank_gate($02D1)
%blank_gate($02EF)
%blank_gate($0337)
%blank_gate($0355)
%blank_gate($0373)
%blank_gate($03C1)
%blank_gate($03E2)
%blank_gate($0401)
%blank_gate($0420)
%blank_gate($043B)
%blank_gate($0479)               ; block header,  uploader $C7:0452
%blank_gate($0498)               ; byte loop,     uploader $C7:0452
%blank_gate($04B6)               ; end of block,  uploader $C7:0452


; ---------------------------------------------------------------------------
; Two bytes per handshake, selected per block
; ---------------------------------------------------------------------------
;
; The loop above still costs one handshake per byte. Port $F5 carries the
; payload while $F6 and $F7 sit idle for the whole block, so a second byte can
; ride in $F6 and halve the number of handshakes. Measured cost per byte falls
; from about 25 SPC700 cycles to 18.
;
; Three bytes is not better than two. Stepping the store index by three means
; the page carry can fall on any of the three stores, so it has to be tested
; three times, and that cancels the saving. Two steps evenly from zero, so the
; index can only wrap on the second store and one test suffices.
;
; The protocol is chosen per block rather than globally. The CPU already sends
; a "kind" byte in the block header, which the S-SMP IPL boot ROM reads and
; discards, caring only that it is non-zero. Sending 2 instead of 1 therefore
; means "two bytes per handshake" to this driver and nothing at all to the IPL.
; That is what keeps the boot upload safe: the uploader at $C7:0252 drives the
; IPL as well as the driver, and the IPL is mask ROM that can only ever read
; one byte per handshake. It keeps sending kind 1 and is not touched.
;
; Only the uploader at $C7:0452 is converted. Counting APU writes by the SPC700
; program counter at the moment of each write, it carries 161,910 of the
; 173,596 bytes the driver receives, or 93%, and never talks to the IPL.
;
; Two entry points into this region are branched to from outside it and must
; keep their addresses: $0EBD, where a data block begins, and $0EFF, where a
; block header is parsed, reached by the bra at $0EBB.

arch spc700

!KIND      = $e6                 ; driver scratch, holds the block's kind byte
!PORT_DEST = $f6                 ; APU ports 2 and 3, the block destination
!TWO_BYTE  = $02                 ; kind value meaning two bytes per handshake

org $0EAB13                      ; SPC $0EBD, where a data block begins

spc_block_start:
    mov   y,!PORT_COUNTER        ; the CPU posts zero to open the data phase
    cmp   y,#$00
    bne   spc_block_start        ; Y leaves this loop as the first store index

spc_dispatch:
    mov   a,!KIND                ; the kind byte stashed by the header parse
    cmp   a,#!TWO_BYTE
    beq   spc_pair_loop

spc_byte_loop:
    cmp   y,!PORT_COUNTER        ; has the CPU posted exactly our index?
    bne   spc_edge
    mov   a,!PORT_DATA
    mov   !PORT_COUNTER,y        ; echo, which releases the CPU
    mov   (!DEST_LOW)+y,a
    inc   y
    bne   spc_byte_loop
    inc   !DEST_PAGE
    bra   spc_byte_loop

spc_edge:
    bpl   spc_dispatch           ; index still ahead of the counter, keep waiting
    bra   spc_header             ; counter jumped, so a new block has begun

spc_pair_loop:
    cmp   y,!PORT_COUNTER        ; the counter now steps by two, as the index does
    bne   spc_edge
    mov   a,!PORT_DATA           ; first byte
    mov   (!DEST_LOW)+y,a
    mov   a,!PORT_DEST           ; second byte, read before the echo releases it
    mov   !PORT_COUNTER,y        ; echo the counter the CPU posted
    inc   y
    mov   (!DEST_LOW)+y,a
    inc   y                      ; index stays even, so this is the only wrap
    bne   spc_pair_loop
    inc   !DEST_PAGE
    bra   spc_pair_loop


org $0EAB55                      ; SPC $0EFF, where a block header is parsed

spc_header:
    mov   a,!PORT_DEST           ; destination low
    mov   y,$f7                  ; destination high
    movw  !DEST_LOW,ya
    mov   y,!PORT_COUNTER        ; the counter that opened this header
    mov   a,!PORT_DATA           ; the kind byte
    mov   !KIND,a                ; stashed for the dispatch above
    mov   !PORT_COUNTER,y        ; echo, releasing the CPU
    cmp   a,#$00
    beq   spc_driver_ready       ; kind zero ends the list
    bra   spc_block_start

org $0EAB7E                      ; SPC $0F28, stock code, a label only
spc_driver_ready:


; ---------------------------------------------------------------------------
; 65816 side: post two bytes per handshake from the uploader at $C7:0452.
;
; Entry:  A 8-bit, X/Y 16-bit, DBR = the bank holding the sample data,
;         X = block length in bytes, Y = source index, the header handshake
;         has completed
; Exit:   jumps to $C7:04B5, the stock end-of-block path, with A holding the
;         last counter posted, and Y advanced by exactly the block length
;
; The first pair goes out with counter zero and without waiting, because the
; header handshake has just synchronised both sides and the driver's block
; start waits for exactly zero. Every later pair waits for the echo of the
; previous counter before touching either data port.
;
; Block lengths are not all even; 45, 4521, 6003 and 6147 all occur. A pair
; loop over an odd length posts one handshake too many and would walk the
; source pointer past the end of the block, so the source start and the byte
; count are saved and Y is recomputed as start plus count rather than trusted
; from the running iny. The driver stores the surplus byte at index len, which
; the next block overwrites because destinations are consecutive.
; ---------------------------------------------------------------------------

arch 65816

!KIND_SITE = $0E846D             ; CPU $C7:046D, the kind byte the header posts
!DATA_ENTRY = $0E8488            ; CPU $C7:0488, the stock data-phase stub
!PAIR_ROUTINE = $0E84EB          ; CPU $C7:04EB, filler used for the pair loop

org !KIND_SITE
    db !TWO_BYTE                 ; tell the driver this block carries pairs

org !DATA_ENTRY
    jmp.w cpu_send_pairs-$8000

org !PAIR_ROUTINE

cpu_send_pairs:
    phy                          ; remember where this block's source began
    phx                          ; and how many bytes it is
    rep #$20
    txa
    inc a                        ; round up so an odd length gets a last pair
    lsr a
    tax                          ; X = number of pairs
    sep #$20

    lda $0000,y                  ; first byte of the first pair
    iny
    sta.l !PORT_DATA0
    lda $0000,y                  ; second byte of the first pair
    iny
    sta.l !PORT_DATA1
    lda #$00                     ; the driver's block start waits for zero
    sta.l !PORT_COUNTER_L
    xba                          ; B = counter, the loop's invariant
    dex
    beq .sent

.pair:
    lda $0000,y                  ; A = first byte, B still holds the counter
    iny
    xba                          ; A = counter, B = first byte

.wait:
    cmp.l !PORT_COUNTER_L        ; wait for the echo of the previous counter
    bne .wait                    ; nothing may touch the data ports until now

    inc a                        ; the counter steps by two, matching the
    inc a                        ; driver index, which now steps by two
    xba                          ; A = first byte, B = counter
    sta.l !PORT_DATA0
    lda $0000,y                  ; A = second byte
    iny
    sta.l !PORT_DATA1
    xba                          ; A = counter, B = second byte
    sta.l !PORT_COUNTER_L        ; posting the counter releases the driver
    xba                          ; restore B = counter for the next pass
    dex
    bne .pair

.sent:
    xba                          ; A = the counter last posted
    pha                          ; park it, the fix-up below needs a 16-bit A
    rep #$20                     ; counter at s+1, count at s+2, start at s+4
    lda $02,s
    clc
    adc $04,s
    tay                          ; Y = source start plus the block length
    sep #$20
    pla                          ; A = counter again
    plx                          ; drop the saved byte count
    plx                          ; drop the saved source start
    jmp.w !RESUME                ; stock path waits for the final echo
