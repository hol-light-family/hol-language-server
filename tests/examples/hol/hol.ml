(* Stands in for HOL Light's hol.ml, so the tests need no HOL Light checkout.
   Checked: ADD_SYM is found here, in the HOL Light directory, and this file
   counts as a base HOL Light file. The project files use ADD_SYM and EVEN. *)

(* A minimal stand-in for the HOL Light directory *)
let ADD_SYM = prove
 (`!m n. m + n = n + m`,
  ARITH_TAC);;

let EVEN = new_definition `EVEN n <=> ?m. n = 2 * m`;;
