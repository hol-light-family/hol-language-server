(* Conversions, built the way the HOL Light tutorial builds them.
   - ADD_SYM_CONV is made from a theorem in lib/util.ml with REWRITE_CONV.
   - MY_CONV combines two conversions with THENC.
   - MY_CONV is then used in a proof (CONV_TAC) and on a theorem (CONV_RULE).
   Checked: Go to Definition and hover on each conversion where it is used,
   and on the theorem a conversion is built from. *)

needs "lib/util.ml";;

let ADD_SYM_CONV = REWRITE_CONV[ADD_SYM_ALT];;

let MY_CONV = ADD_SYM_CONV THENC NUM_REDUCE_CONV;;

let MY_CONV_THM = prove
 (`1 + 2 = 3`,
  CONV_TAC MY_CONV);;

let MY_RULE_THM = CONV_RULE MY_CONV (ARITH_RULE `2 + 1 = 3`);;
