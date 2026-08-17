; Street Fighter Alpha 2 / Zero 2, skip a base sample list that is already loaded.
;
; ---------------------------------------------------------------------------
; What repeats, and why it is safe to skip
; ---------------------------------------------------------------------------
;
; The sound engine at $C7:005B is called with a music or stage list id in A and
; three sample group ids in direct page $80, $81 and $82. It resets an
; allocator to SPC $1500, uploads the list named by the id, records where the
; allocator finished at $7E:2000, then walks the three groups from there.
;
; It already has a path that skips the list. Called with id zero it jumps to
; $C7:00EE instead, restores the allocator from $7E:2000, and walks the groups
; alone. That path is stock, it is exercised constantly, and it is what this
; patch steers into: rather than adding a way to skip, it recognises when the
; skip is correct and rewrites the id to zero.
;
; The allocator is a bump allocator restarted at $1500 on every load, and the
; list is always placed first. Every group therefore sits above whatever the
; list occupies, and no group upload can ever write into the list's own region.
; The only thing that overwrites a base list is a different base list. So the
; question "is the list still resident" reduces to "was the last list loaded the
; same one", which is a byte compare.
;
; Measured rather than argued. Replaying every upload of an eighteen fighter
; tour against a shadow of sound RAM, on four builds, the two conditions agree
; exactly:
;
;   build            base lists   same as previous   of those still resident
;   USA cartridge       265             51                    51
;   USA chip-free       240             43                    43
;   Japan cartridge     234             41                    41
;   Japan chip-free     254             46                    46
;
; 181 candidates across the four, no case where a list was still resident
; without being the same as the previous one, and no case the other way round.
;
; What the patch then saves was measured by building one cartridge that differs
; from another in this patch alone and running the same tour on both:
;
;   build                 blocks sent      bytes sent
;   USA without            6,903            9,615,932
;   USA with               5,978            8,775,166
;   Japan without          5,728            8,403,872
;   Japan with             5,317            8,100,532
;
; 840,766 bytes on the USA cartridge, 8.7%, about 13 seconds of driver time
; across an hour of play, and it is the largest single saving left in the sound
; path. It is smaller than the 1,149,936 bytes the replay predicts because the
; two runs stop being frame identical at the first skip.
;
; ---------------------------------------------------------------------------
; What changes for the player
; ---------------------------------------------------------------------------
;
; The base list carries the music sequence as well as the stage samples, so a
; skipped list means the sequence is not sent again and the music is not
; restarted. This fires when the same stage is loaded twice running, which is
; the second and third rounds of a fight. The arcade lets the music run across
; rounds; the SNES release restarts it. gizaha's MSU-1 patch stops the restart
; deliberately for the same reason.
;
; That is a change to what the player hears, and no measurement here settles
; whether it sounds right. What is settled is that every block that does get
; sent still matches its source, that no image loses a block, and that the
; sample data the groups land on is unchanged.
;
; ---------------------------------------------------------------------------
; The marker
; ---------------------------------------------------------------------------
;
; $1F3F and $1F40 hold a two byte magic, $5A and $A5, and $1F41 the id of the
; last list actually uploaded. The magic is there because work RAM does not
; come up zeroed on a console, a lesson this project already paid for once: a
; marker with no validity check would read garbage after power-on and could
; skip the first load. Both the magic and the id have to match, so garbage
; matches with probability one in sixteen million, and after the first real
; load the marker is always correct.
;
; The address was moved up one byte after measurement, and the correction is
; worth recording because the first version looked right and was not. The
; region survey this project uses reports which addresses a run reads or
; writes, and it named $1F3E to $1FC6 as touched in neither direction. Watching
; every write to those three bytes across an eighteen fighter tour tells a
; different story: $1F3E is written 432 times, from four sites in bank $C0, and
; $1FC6 7,888 times from $C0:01DA. Both ends of the run are live and only the
; inside is free, so the first magic byte was sitting on a live variable.
;
; Moving off it changed no measured total. The same tour on a build with the
; record at $1F3F sends the same 5,978 blocks and the same 8,775,166 bytes as
; the build whose magic sat on $1F3E. So the collision was real and is fixed,
; and it is not what declines the repeats that remain unskipped. What does is
; not established.
;
; A corrupt record can only refuse a skip, never invent one. That is what the
; two magic bytes are for and it holds either way.
;
; $1F3F to $1FC5 is the run that survives the write watch. The sound transfer's
; private stack lives at $1FE0 and grows down, reaching $1FD2 at the deepest,
; well clear of the three bytes used here.
;
; Entry:  reached by jsr from $C7:0069, which is the lda #$1500 that starts the
;         allocator. A and X and Y are 16 bit, the direct page is zero, the
;         data bank is $C7 because the entry did phk plb, which is why every
;         access to the marker below is long addressed
; Exit:   rts with A 16 bit holding $1500, exactly what the replaced
;         instruction left, and the id on the stack either untouched or zeroed
;
; The id sits at 3,s: the entry pushed it with pha at $C7:0064 and the jsr that
; reaches here pushed two more bytes on top of it.
; ---------------------------------------------------------------------------

lorom

!MARKER_MAGIC_LOW  = $001F3F
!MARKER_MAGIC_HIGH = $001F40
!MARKER_ID         = $001F41

!MAGIC_LOW  = $5A
!MAGIC_HIGH = $A5

!ALLOCATOR_START = $1500
!ID_ON_STACK = $03

!ROUTINE = $F600                ; reached as $C7:F600 through the window

org $0E8069
    jsr !ROUTINE                ; replaces lda #$1500, same three bytes

org $0FF600

repeat_load:
    sep #$20
    lda !ID_ON_STACK,s
    beq .done                   ; id zero already skips the list

    pha                         ; keep the id for the compare and the record
    lda.l !MARKER_MAGIC_LOW
    cmp #!MAGIC_LOW
    bne .remember
    lda.l !MARKER_MAGIC_HIGH
    cmp #!MAGIC_HIGH
    bne .remember
    lda.l !MARKER_ID
    cmp $01,s                   ; the id kept above
    bne .remember

    pla
    lda #$00
    sta !ID_ON_STACK,s          ; the stock id-zero path does the rest
    bra .done

.remember:
    pla
    sta.l !MARKER_ID
    lda #!MAGIC_LOW
    sta.l !MARKER_MAGIC_LOW
    lda #!MAGIC_HIGH
    sta.l !MARKER_MAGIC_HIGH

.done:
    rep #$20
    lda.w #!ALLOCATOR_START
    rts

warnpc $0FF700
