(* Loads.
   - `needs "lib/util.ml"` resolves: Go to Definition on the file name opens it.
   - `needs "missing.ml"` does not: it is reported as a missing load.
   Checked: the document symbols are MY_THM and x. x calls a function that is
   defined nowhere. *)

needs "lib/util.ml";;
needs "missing.ml";;

let MY_THM = prove
 (`!n. EVEN n ==> EVEN (n + n)`,
  GEN_TAC THEN
  REWRITE_TAC[EVEN; ADD_SYM_ALT] THEN
  STRIP_TAC THEN ARITH_TAC);;

let x = unknown_function 1;;
