(* Like fusion.ml: items of a module without `;;`, then `include`.
   Checked: kfun2 is found here, and ctx.ml can use it through `include Kernel`. *)
module Kernel = struct

  let kfun x = x

  let kfun2 y =
    let z = y in z

end;;

include Kernel;;
