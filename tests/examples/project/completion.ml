(* Name and member completion.
   Loads lib/util.ml for ADD_SYM_ALT; the base files give ADD_SYM and Kernel.
   Gadget and Gadget.Inner are defined here and stay closed until `open Gadget`,
   so their members complete with qualified labels before it and short ones after.
   The mid-word probe completes with the cursor inside the word, not after it.
   Checked: the labels and kinds in the `complete` comments. Docs, edit spans,
   and commit characters stay procedural in test_service.py. *)

needs "lib/util.ml";;

module Gadget = struct
  let widget x = x
  let gimbal x = x
  (* complete: let gimb => none *)

  module Inner = struct
    let sprocket y = y
  end
end

let probe_tac = 1;;
(* complete: let probe_tac => none *)

let z = ADD_S;;
(* complete: let z = ADD_S => ADD_SYM:theorem ADD_SYM_ALT:theorem *)

let z = widg;;
(* complete: let z = widg => Gadget.widget:value *)

let z = sprock;;
(* complete: let z = sprock => Gadget.Inner.sprocket:value *)

let z = Inne;;
(* complete: let z = Inne => Gadget.Inner:module *)

let z = Gadg;;
(* complete: let z = Gadg => Gadget:module *)

let q = Gadget.widg;;
(* complete: let q = Gadget.widg => widget:value *)

let q = Gadget.Inne;;
(* complete: let q = Gadget.Inne => Inner:module *)

let z = Kernel.kfun;;
(* complete: let z = Kernel.kfun => kfun:value kfun2:value *)

let m = Kernel.kfun
(* complete: let m = Kernel.kf => kfun:value kfun2:value *)

let w = Kernel.;;
(* complete: let w = Kernel. => kfun:value kfun2:value *)

open Gadget;;

let v = widg;;
(* complete: let v = widg => widget:value *)

let z = zzz_missing;;
(* complete: let z = zzz_missing => none *)

let z = Kernel.zzz;;
(* complete: let z = Kernel.zzz => none *)

let t = `!E. E`;;
(* complete: let t = `!E. E => none *)

(* Gadget widget sprocket *)
(* complete: Gadget widget => none *)

let greeting = "hello Gadget";;
(* complete: hello Gadget => none *)

let (+/) x y = x;;

let sum = 1 + 2;;
(* complete: 1 + => none *)
