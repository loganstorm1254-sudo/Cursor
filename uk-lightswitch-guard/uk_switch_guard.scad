// UK 1-gang light-switch guard
// Inspired by the hinged "Switch Guard" concept (MakerWorld #255143),
// re-dimensioned for a standard British 86×86 mm rocker faceplate.
//
// Print: PLA/PETG, 0.2 mm layers, ≥2 walls, 15–25% infill, no supports
 //        if printed in the suggested orientation.
// Install: loosen the two faceplate screws, slide the base under the
 //         screw heads (or remove screws and refit through the slots),
 //         snap the lid onto the hinge posts / insert 1.75 mm filament pins.
//
// part = "assembly" | "base" | "lid" | "plate"  (plate = both parts laid flat)

/* [Which part] */
part = "plate"; // [assembly, base, lid, plate]

/* [UK faceplate] */
screw_centres = 60.3;   // BS standard 1-gang fixing centres (mm)
screw_slot_w  = 4.4;    // clearance for M3.5 countersunk screws
screw_slot_l  = 7.0;    // elongated so it still fits slightly off-centre plates
plate_clearance = 0.4;  // extra breathing room around the rocker

/* [Rocker aperture — fits typical MK/Crabtree/Logic Plus narrow rockers;
    bump rocker_w to ~32 for "wide rocker" / accessible styles] */
rocker_w = 28;
rocker_h = 38;
rocker_protrusion = 8;  // how far the rocker sticks out past the plate face

/* [Base] */
base_w = 40;
base_h = 78;
base_t = 2.4;
base_fillet = 3;

/* [Lid / cover] */
lid_wall = 2.0;
lid_gap  = 0.35;        // clearance between lid and base when closed
lid_depth = 13;         // cavity depth above the base face
lid_flare = 4;          // how much wider the scoop is than the aperture
tab_len = 10;
tab_w = 14;
tab_t = 2.2;

/* [Hinge] */
hinge_pin_d = 1.75;     // 1.75 mm filament pin (or 1.75 mm rod)
hinge_ball_d = 5.6;
hinge_clearance = 0.35;
hinge_knuckle_w = 5.2;
hinge_span = 24;        // centre-to-centre of the two hinge posts

/* [Catch — G3-style: resists a pure upward tug] */
catch_enabled = true;
catch_lip = 1.2;
catch_overhang = 1.4;

$fn = 48;
eps = 0.02;

// ---------------------------------------------------------------------------
module rounded_rect(size, r) {
    w = size[0]; h = size[1]; t = size[2];
    rr = min(r, w/2 - 0.01, h/2 - 0.01);
    linear_extrude(t)
        offset(r = rr)
            square([w - 2*rr, h - 2*rr], center = true);
}

module screw_slot() {
    hull() {
        translate([-(screw_slot_l - screw_slot_w)/2, 0, -eps])
            cylinder(d = screw_slot_w, h = base_t + 2*eps);
        translate([ (screw_slot_l - screw_slot_w)/2, 0, -eps])
            cylinder(d = screw_slot_w, h = base_t + 2*eps);
    }
}

module base() {
    aperture_w = rocker_w + 2*plate_clearance;
    aperture_h = rocker_h + 2*plate_clearance;
    hinge_y = aperture_h/2 + hinge_ball_d/2 + 1.2;

    difference() {
        union() {
            // main plate
            rounded_rect([base_w, base_h, base_t], base_fillet);

            // raised rim around the aperture (adds stiffness + catch ledge)
            translate([0, 0, base_t - eps])
                difference() {
                    rounded_rect([aperture_w + 2*lid_wall + 2,
                                  aperture_h + 2*lid_wall + 2,
                                  1.6], 2);
                    translate([0, 0, -eps])
                        rounded_rect([aperture_w, aperture_h, 1.6 + 2*eps], 1.2);
                }

            // hinge posts (male balls with filament-pin through-holes)
            for (sx = [-1, 1])
                translate([sx * hinge_span/2, hinge_y, base_t + hinge_ball_d/2 - 0.4])
                    hinge_post();

            // G3-style catch ledge at the bottom of the aperture rim
            if (catch_enabled)
                translate([0, -(aperture_h/2 + 0.8), base_t + 0.6])
                    cube([aperture_w * 0.55, catch_overhang, 1.2], center = true);
        }

        // rocker window
        translate([0, 0, -eps])
            rounded_rect([aperture_w, aperture_h, base_t + 4], 1.5);

        // screw slots at BS centres
        translate([0,  screw_centres/2, 0]) rotate([0, 0, 90]) screw_slot();
        translate([0, -screw_centres/2, 0]) rotate([0, 0, 90]) screw_slot();
    }
}

module hinge_post() {
    difference() {
        union() {
            sphere(d = hinge_ball_d);
            // short neck into the base
            translate([0, 0, -hinge_ball_d/2])
                cylinder(d1 = hinge_ball_d * 0.7, d2 = hinge_ball_d * 0.55, h = hinge_ball_d/2);
        }
        // filament pin hole through the ball (backup if the snap fails)
        rotate([0, 90, 0])
            cylinder(d = hinge_pin_d + 0.15, h = hinge_ball_d + 2, center = true);
    }
}

module lid() {
    aperture_w = rocker_w + 2*plate_clearance;
    aperture_h = rocker_h + 2*plate_clearance;
    // Flared scoop: wider/taller at the open face, narrower toward the hinge back
    face_w = aperture_w + 2*lid_wall + 2*lid_flare + 4;
    face_h = aperture_h + 2*lid_wall + 6;
    back_w = aperture_w + 2*lid_wall;
    back_h = aperture_h + 2*lid_wall - 2;
    inner_w = aperture_w + 2*lid_gap;
    inner_h = aperture_h + 2*lid_gap;
    cavity_d = max(lid_depth, rocker_protrusion + 4);
    hinge_y = aperture_h/2 + hinge_ball_d/2 + 1.2;

    difference() {
        union() {
            // Scoop shell — flared mouth, tucked toward the hinge
            hull() {
                // open face (against the wall plate)
                translate([0, -1.5, 0])
                    rounded_rect([face_w, face_h, 0.9], 4);
                // mid flare
                translate([0, 0.2, cavity_d * 0.45])
                    rounded_rect([face_w - 2, face_h - 2, 0.8], 3.5);
                // closed back (near hinge / rocker face)
                translate([0, 1.5, cavity_d - 0.9])
                    rounded_rect([back_w, back_h, 0.9], 2.5);
            }

            // finger tab at the bottom of the scoop
            translate([0, -(face_h/2 + tab_len/2 - 2.5), 0])
                hull() {
                    rounded_rect([tab_w, tab_len, tab_t], 2.5);
                    translate([0, tab_len/2, cavity_d * 0.15])
                        rounded_rect([tab_w - 2, 2, tab_t], 1);
                }

            // hinge knuckles (female sockets)
            // z chosen so the socket centres line up with the base posts
            // when the lid is placed at z = base_t + 0.15
            for (sx = [-1, 1])
                translate([sx * hinge_span/2, hinge_y, hinge_ball_d/2 - 0.55])
                    hinge_knuckle();
        }

        // inner cavity for the rocker
        translate([0, 0, -eps])
            hull() {
                translate([0, -1.0, 0])
                    rounded_rect([inner_w + 2, inner_h + 3, 0.6], 2);
                translate([0, 0.8, cavity_d - lid_wall])
                    rounded_rect([inner_w - 1, inner_h - 2, 0.6], 1.2);
            }

        // open the underside so it seats over the base rim
        translate([0, 0, -eps])
            rounded_rect([inner_w + 1.6, inner_h + 1.6, 1.3], 1.5);

        // G3 catch relief
        if (catch_enabled)
            translate([0, -(inner_h/2) + 0.2, 0.9])
                cube([inner_w * 0.5, 2.2, 1.6], center = true);
    }

    // catch tooth on the lid (hooks under the base ledge)
    if (catch_enabled)
        translate([0, -(inner_h/2) - 0.15, 1.0])
            cube([inner_w * 0.42, catch_lip, 1.0], center = true);
}

module hinge_knuckle() {
    od = hinge_ball_d + 2*hinge_clearance + 2.2;
    // Keep the knuckle above the print bed (z>=0 in lid coordinates).
    difference() {
        hull() {
            intersection() {
                sphere(d = od);
                translate([0, 0, od/2])
                    cube([od + 1, od + 1, od], center = true);
            }
            translate([0, -od/2 + 0.4, od * 0.25])
                cube([hinge_knuckle_w, 0.6, od * 0.5], center = true);
        }
        // socket for the ball
        sphere(d = hinge_ball_d + 2*hinge_clearance);
        // filament pin hole (aligned with the post hole)
        rotate([0, 90, 0])
            cylinder(d = hinge_pin_d + 0.2, h = od + 2, center = true);
        // assembly slot from the underside so the knuckle can snap over the ball
        translate([0, 0, -od/2])
            cube([hinge_ball_d * 0.55, od, od], center = true);
    }
}

module assembly() {
    base();
    // lid shown closed, slightly above the base
    color("SteelBlue", 0.85)
        translate([0, 0, base_t + 0.15])
            lid();
}

module plate() {
    // print layout: both parts flat on the bed
    translate([-base_w/2 - 8, 0, 0]) base();
    translate([ base_w/2 + 18, 0, 0]) lid();
}

if (part == "base") base();
else if (part == "lid") lid();
else if (part == "plate") plate();
else assembly();
