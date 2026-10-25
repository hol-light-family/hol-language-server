(* Local names: a `let ... in` inside a definition, and function parameters.
   Go to Definition on a local name should jump to where it is bound, not to
   the top-level definitions with the same names at the end of this file.
   After those, more scope rules: shadowing, where a scope ends, type names. *)

let NESTED =
  let y = 1 in
  y;;

let ADD_FUN = fun x y ->
  x + y;;

let add_params a b =
  a + b;;

let y = 5;;
let x = 0;;

(* The second `let s` uses the first s; the last s is the second one. *)
let SHADOW =
  let s = 1 in
  let s = s + 1 in
  s;;

(* q is inner's parameter only inside inner: after `in` it is unbound. *)
let SCOPE_END p =
  let inner q = q + p in
  inner q;;

(* w is bound in its own arm only, not in the next one. *)
let ARMS v =
  match v with
    Some w -> w
  | None -> w;;

(* `term` in the annotation is a type, not a parameter. *)
let TYPED (t: term) = t;;
