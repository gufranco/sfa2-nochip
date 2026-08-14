; Street Fighter Zero 2 (Japan), Shin Akuma always unlocked.
;
; ---------------------------------------------------------------------------
; What this is
; ---------------------------------------------------------------------------
;
; Shin Akuma is already in the retail cartridge. He is not added by this patch
; and no graphics or character data are touched. He sits behind a cheat that
; went unnoticed for twenty five years and was only documented in January 2021:
;
;   1. enter the initials K, A, J in the high score table
;   2. return to the title screen
;   3. hold L, X, Y and Start on the controller in port two while player one
;      selects Versus mode
;   4. at the character select, hold Start while choosing Akuma
;
; Steps 1 to 3 do nothing except set one flag in work RAM. Step 4 is the actual
; selection and is left alone here. This patch removes steps 1 to 3 by setting
; that flag unconditionally, which is the same simplification gizaha describes
; in his Zeldix changelog of 2021-06-20 as "Simplified Shin Akuma selection
; code (removed the P2 L,X,Y + Start check at title screen)".
;
; ---------------------------------------------------------------------------
; The gate, as Capcom wrote it
; ---------------------------------------------------------------------------
;
; The whole cheat is one routine at $C0:EC6E, called from $C0:C670. Recovered
; by searching the ROM for cmp #$5060, the SNES joypad word for L, X, Y and
; Start held together, which has exactly one match in executable code:
;
;   C0ECA0  08           php
;   C0EC6F  c2 30        rep #$30
;   C0EC71  ad 05 1b     lda $1b05        screen state, must be negative
;   C0EC74  10 27        bpl $ec9d
;   C0EC76  ad 09 1b     lda $1b09        the unlock flag
;   C0EC79  c9 4b 4a     cmp #$4a4b
;   C0EC7C  f0 1f        beq $ec9d        already unlocked, nothing to do
;   C0EC7E  af 04 fe 7e  lda $7efe04      initials, first two letters
;   C0EC82  c9 4b 41     cmp #$414b       "K" then "A"
;   C0EC85  d0 16        bne $ec9d
;   C0EC87  af 05 fe 7e  lda $7efe05      initials, second and third letters
;   C0EC8B  c9 41 4a     cmp #$4a41       "A" then "J"
;   C0EC8E  d0 0d        bne $ec9d
;   C0EC90  a5 b0        lda $b0          buttons held on controller two
;   C0EC92  c9 60 50     cmp #$5060       L | X | Y | Start
;   C0EC95  d0 06        bne $ec9d
;   C0EC97  a9 4b 4a     lda #$4a4b
;   C0EC9A  8d 09 1b     sta $1b09        the flag, and the only thing it does
;   C0EC9D  28           plp
;   C0EC9E  60           rts
;
; The two overlapping reads at $7E:FE04 and $7E:FE05 are how three letters are
; checked with two sixteen bit compares: $FE04 holds "K", $FE05 "A", $FE06 "J",
; so the pairs read back as $414B and $4A41 on a little endian bus.
;
; The flag is consumed at $C0:CA7F, which is left exactly as it shipped:
;
;   C0CA82  lda $1b09
;   C0CA85  cmp #$4a4b       unlocked?
;   C0CA88  bne $cacf
;   C0CA8C  lda $1c1c        which side is choosing, zero is player one
;   C0CA8F  bne $cab1
;   C0CA91  lda $07a2        the character under the cursor
;   C0CA94  cmp #$02         Akuma
;   C0CA96  d0 37 bne $cacf
;   C0CA98  lda $ab          buttons held, high byte
;   C0CA9A  bit #$10         Start
;   C0CA9C  f0 31 beq $cacf
;   C0CA9E  ldx #$14         the Shin Akuma variant
;   C0CAA0  stx $1c20
;
; So holding Start over Akuma stays the way in, exactly as on a stock cart.
;
; ---------------------------------------------------------------------------
; The change
; ---------------------------------------------------------------------------
;
; Two bytes. The precondition test at $C0:EC71 becomes a branch straight to the
; store at $C0:EC97, so the routine's only remaining job is to set the flag.
;
; Branching from $C0:EC71 rather than from the initials test at $C0:EC7E is
; deliberate. $1B05 is read here and never written by any absolute store in the
; ROM, and it reads back as $000F during the attract sequence, so bit 15 is
; clear and bpl would have taken the exit before any of the cheat's own tests
; ran. Skipping only the initials and the joypad check, which is the narrower
; edit it looks like it should be, leaves the routine gated on a condition that
; is not satisfied when the routine is called. Verified by reading the flag out
; of work RAM under emulation at frame 3000: stock leaves $7E:1B09 at $0000,
; this patch leaves it at $4A4B.
;
; The bytes from $C0:EC73 to $C0:EC96 are now unreachable and are left in place
; rather than blanked, so the cheat's own code stays readable in the ROM.
;
; asar is told the plain LoROM mapping, under which file offset F is bank
; F >> 15 at address $8000 + (F & $7FFF). The game runs this code from the $C0
; window, but a bra is relative, so the bank it executes from does not matter.
;
;   CPU  $C0:ECA3 ->  file $00ECA3  ->  $01:ECA3
;
; The gate is byte identical in both regional ROMs; only its address moves, by
; the same $32 that separates the two builds' code here. The Japanese routine
; begins at $C0:ECA0 against $C0:EC6E in the USA ROM, so the screen test sits at
; $C0:ECA3 and the store at $C0:ECC9.

lorom

!PRECONDITION = $01ECA3          ; the lda $1b05 screen test
!SET_FLAG     = $01ECC9          ; the unconditional store

org !SET_FLAG
set_flag:                        ; a label only, no bytes are emitted here

org !PRECONDITION
    bra set_flag                 ; the flag is now set on every call
