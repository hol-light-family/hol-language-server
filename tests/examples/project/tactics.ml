(* Hover, Go to Definition, and symbols on tactics.
   - HELPER_TAC has a parameter `th`, named like the global th.
   - MY_TAC holds a string with a backquote: NOT_A_REFERENCE in it is not a name.
   - MY_TAC is not ended by `;;`, and OTHER_TAC after it must still be found.
   - OTHER_TAC uses MY_TAC, which uses HELPER_TAC: a chain of definitions. *)

needs "lib/util.ml";;

let th = ADD_SYM_ALT;;

(* A tactic with a parameter named like the global th *)
let HELPER_TAC th =
  REWRITE_TAC[th; ADD_SYM_ALT];;

let MY_TAC =
  let msg = "not \
NOT_A_REFERENCE `ADD_SYM`" in
  fun th -> HELPER_TAC th
let OTHER_TAC = MY_TAC ADD_SYM_ALT;;
