(* ADD_SYM_ALT: a theorem that the other project files use.
   Checked: hover on it from tactics.ml shows its statement, and
   `needs "lib/util.ml"` in main.ml opens this file. *)

let ADD_SYM_ALT = prove
 (`!m n. n + m = m + n`,
  REWRITE_TAC[ADD_SYM]);;
