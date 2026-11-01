(* The word binders: forall, exists, existsunique, lambda. HOL Light reads the
   first three as the symbol ones by default, and prints theorems with them.
   Checked: a definition under forall introduces the constant after it, not
   forall, and one under exists introduces nothing; a name each word binds hides the constant in the binder and its
   body; a longer name holding a word binds nothing. *)

let R2 = define `R2 = 1`;;
let WB_FOO = new_definition `forall x. wb_foo x = x`;;
let WB_BAR = define `forall x y. wb_bar x y = x`;;

let WB_NONE = new_definition `exists y. wb_none y = y`;;
(* complete: WB_NONE = new_definition `exis => none *)

let USES = `wb_foo 1 = wb_bar 1 2`;;

(* goto: wb_foo 1 => wb_foo x = x *)
(* goto: wb_bar 1 => wb_bar x y *)
(* complete: USES = `wb_fo => wb_foo:constant *)

let ALL_THEM = `(forall R2. R2 = 3) /\ (exists R2. R2 = 4) /\ (existsunique R2. R2 = 5) /\ (lambda R2. R2 + 6) = f /\ R2 = 7`;;

(* goto: R2 = 3 => nowhere *)
(* goto: R2 = 4 => nowhere *)
(* goto: R2 = 5 => nowhere *)
(* goto: R2 + 6 => nowhere *)
(* goto: R2 = 7 => R2 = 1 *)
(* hover: R2 = 3 => none *)
(* complete: (forall R => none *)
(* complete: (exists R => none *)
(* complete: (existsunique R => none *)
(* complete: (lambda R => none *)
(* complete: (forall R2. R => none *)
(* complete: f /\ R => R2:constant *)

let LONGER = `forall_thm R2 = 8 /\ my_exists R2 = 9`;;

(* goto: R2 = 8 => R2 = 1 *)
(* goto: R2 = 9 => R2 = 1 *)
(* complete: forall_thm R => R2:constant *)
