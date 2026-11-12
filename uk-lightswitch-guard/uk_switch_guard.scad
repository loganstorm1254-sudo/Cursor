// UK 1-gang rocker light-switch guard
// For the classic British moulded plate: square ~86×86 mm faceplate with
// LEFT/RIGHT fixing screws at 60.3 mm centres and a centred rocker.
// Concept inspired by MakerWorld Switch Guard #255143 (hinged scoop lid).
//
// Print: PLA/PETG, 0.2 mm, ≥2 walls, 15–25% infill, no supports
// Install: loosen the two faceplate screws, slide the base under the heads
//         (or remove and refit through the slots), snap the lid on.
//         If a hinge snap wears out, push 1.75 mm filament through as a pin.
//
// part = "assembly" | "base" | "lid" | "plate"

/* [Which part] */
part = "plate"; // [assembly, base, lid, plate]

/* [UK faceplate — matches the photo: screws LEFT & RIGHT of the rocker] */
screw_centres = 60.3;   // horizontal BS 1-gang fixing centres (mm)
screw_slot_w  = 4.5;    // clearance for M3.5 countersunk screws
screw_slot_l  = 7.5;    // elongated for slight plate tolerance
plate_clearance = 0.6;  // breathing room around the rocker

/* [Rocker aperture — sized for a typical narrow UK rocker as in the photo.
    Measure yours: rocker face is often ~20–22 × 28–32 mm.] */
rocker_w = 24;
rocker_h = 34;
rocker_protrusion = 7;

/* [Base — landscape bar spanning the L/R screws] */
base_w = 76;            // must clear screw centres + screw-head washers
base_h = 52;
base_t = 2.4;
base_fillet = 4;

/* [Lid / cover] */
lid_wall = 2.0;
lid_gap  = 0.4;
lid_depth = 12;
lid_flare = 5;
tab_len = 11;
tab_w = 16;
tab_t = 2.2;

/* [Hinge — above the rocker, lid flips UP] */
hinge_pin_d = 1.75;
hinge_ball_d = 5.6;
hinge_clearance = 0.35;
hinge_knuckle_w = 5.2;
hinge_span = 22;

/* [Catch — resists a pure upward tug] */
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
    // Horizontal slot (long axis along X) for L/R faceplate screws
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
    hinge_y = aperture_h/2 + hinge_ball_d/2 + 1.0;

    difference() {
        union() {
            rounded_rect([base_w, base_h, base_t], base_fillet);

            // Raised rim around the rocker window
            translate([0, 0, base_t - eps])
                difference() {
                    rounded_rect([aperture_w + 2*lid_wall + 2.5,
                                  aperture_h + 2*lid_wall + 2.5,
                                  1.6], 2.2);
                    translate([0, 0, -eps])
                        rounded_rect([aperture_w, aperture_h, 1.6 + 2*eps], 1.4);
                }

            // Hinge posts (male balls) above the rocker
            for (sx = [-1, 1])
                translate([sx * hinge_span/2, hinge_y, base_t + hinge_ball_d/2 - 0.4])
                    hinge_post();

            // G3-style catch ledge under the rocker
            if (catch_enabled)
                translate([0, -(aperture_h/2 + 0.8), base_t + 0.6])
                    cube([aperture_w * 0.55, catch_overhang, 1.2], center = true);
        }

        // Rocker window
        translate([0, 0, -eps])
            rounded_rect([aperture_w, aperture_h, base_t + 4], 1.6);

        // LEFT / RIGHT screw slots at BS centres
        translate([-screw_centres/2, 0, 0]) screw_slot();
        translate([ screw_centres/2, 0, 0]) screw_slot();
    }
}

module hinge_post() {
    difference() {
        union() {
            sphere(d = hinge_ball_d);
            translate([0, 0, -hinge_ball_d/2])
                cylinder(d1 = hinge_ball_d * 0.7, d2 = hinge_ball_d * 0.55, h = hinge_ball_d/2);
        }
        rotate([0, 90, 0])
            cylinder(d = hinge_pin_d + 0.15, h = hinge_ball_d + 2, center = true);
    }
}

module lid() {
    aperture_w = rocker_w + 2*plate_clearance;
    aperture_h = rocker_h + 2*plate_clearance;
    face_w = aperture_w + 2*lid_wall + 2*lid_flare + 4;
    face_h = aperture_h + 2*lid_wall + 6;
    back_w = aperture_w + 2*lid_wall;
    back_h = aperture_h + 2*lid_wall - 2;
    inner_w = aperture_w + 2*lid_gap;
    inner_h = aperture_h + 2*lid_gap;
    cavity_d = max(lid_depth, rocker_protrusion + 4);
    hinge_y = aperture_h/2 + hinge_ball_d/2 + 1.0;

    difference() {
        union() {
            // Flared scoop — wider at the plate face, tucked toward the hinge
            hull() {
                translate([0, -1.5, 0])
                    rounded_rect([face_w, face_h, 0.9], 4);
                translate([0, 0.2, cavity_d * 0.45])
                    rounded_rect([face_w - 2, face_h - 2, 0.8], 3.5);
                translate([0, 1.5, cavity_d - 0.9])
                    rounded_rect([back_w, back_h, 0.9], 2.5);
            }

            // Finger tab at the bottom
            translate([0, -(face_h/2 + tab_len/2 - 2.5), 0])
                hull() {
                    rounded_rect([tab_w, tab_len, tab_t], 2.5);
                    translate([0, tab_len/2, cavity_d * 0.15])
                        rounded_rect([tab_w - 2, 2, tab_t], 1);
                }

            // Female hinge knuckles
            for (sx = [-1, 1])
                translate([sx * hinge_span/2, hinge_y, hinge_ball_d/2 - 0.55])
                    hinge_knuckle();
        }

        // Inner cavity
        translate([0, 0, -eps])
            hull() {
                translate([0, -1.0, 0])
                    rounded_rect([inner_w + 2, inner_h + 3, 0.6], 2);
                translate([0, 0.8, cavity_d - lid_wall])
                    rounded_rect([inner_w - 1, inner_h - 2, 0.6], 1.2);
            }

        translate([0, 0, -eps])
            rounded_rect([inner_w + 1.6, inner_h + 1.6, 1.3], 1.5);

        if (catch_enabled)
            translate([0, -(inner_h/2) + 0.2, 0.9])
                cube([inner_w * 0.5, 2.2, 1.6], center = true);
    }

    if (catch_enabled)
        translate([0, -(inner_h/2) - 0.15, 1.0])
            cube([inner_w * 0.42, catch_lip, 1.0], center = true);
}

module hinge_knuckle() {
    od = hinge_ball_d + 2*hinge_clearance + 2.2;
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
        sphere(d = hinge_ball_d + 2*hinge_clearance);
        rotate([0, 90, 0])
            cylinder(d = hinge_pin_d + 0.2, h = od + 2, center = true);
        translate([0, 0, -od/2])
            cube([hinge_ball_d * 0.55, od, od], center = true);
    }
}

module assembly() {
    base();
    color("SteelBlue", 0.85)
        translate([0, 0, base_t + 0.15])
            lid();
}

module plate() {
    translate([0, base_h/2 + 14, 0]) base();
    translate([0, -(base_h/2 + 18), 0]) lid();
}

if (part == "base") base();
else if (part == "lid") lid();
else if (part == "plate") plate();
else assembly();
