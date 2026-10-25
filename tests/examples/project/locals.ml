(* Local names: a `let ... in` inside a definition, and function parameters.
   Go to Definition on a local name should jump to where it is bound, not to
   the top-level definitions with the same names at the end of this file.
   Not supported yet: the tests on this file are marked xfail. *)

let NESTED =
  let y = 1 in
  y;;

let ADD_FUN = fun x y ->
  x + y;;

let add_params a b =
  a + b;;

let y = 5;;
let x = 0;;
