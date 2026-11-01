(* Simple updates of load_path, each applying to the loads after it.
   vendor/ and later/ are not root paths. prefer.ml and keep.ml also sit in
   this directory. An update searches before or after the root paths, by its form.
   Checked: where Go to Definition on each load jumps, the one missing load,
   and what its path completes to. *)

needs "too_early.ml";; (* diagnostic: "too_early.ml" => File not found: too_early.ml *)
(* complete: needs "too_e => none *)

(* load_path := "later" :: !load_path;; *)
load_path := "vendor" :: !load_path;;

needs "vendored.ml";;
(* goto: needs "vendored.ml +7 => let vendor_vendored @load_path/vendor/vendored.ml *)
(* complete: needs "vendored => vendored.ml:file *)

needs "prefer.ml";;
(* goto: needs "prefer.ml +7 => let vendor_prefer @load_path/vendor/prefer.ml *)

load_path := !load_path @ ["later"];;

needs "keep.ml";;
(* goto: needs "keep.ml +7 => let top_keep @load_path/keep.ml *)

needs "only_later.ml";;
(* goto: needs "only_later.ml +7 => let later_only @load_path/later/only_later.ml *)
