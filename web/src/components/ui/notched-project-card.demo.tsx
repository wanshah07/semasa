import { NotchedProjectCard } from "@/components/ui/notched-project-card";

/* Three cards on Semasa's own subjects. The covers are real Unsplash photographs (searched 29 Sep 2026), each card
   linking to its photo's page, which is the attribution Unsplash asks for. The app's own use is the Design library
   (components/DesignLibrary.jsx), where the covers are Wan's photographs. */

const LAB = "https://images.unsplash.com/photo-1658387575528-88b316c42371?auto=format&fit=crop&w=900&q=75";
const SKIN = "https://images.unsplash.com/photo-1612817288484-6f916006741a?auto=format&fit=crop&w=900&q=75";
const SHELF = "https://images.unsplash.com/photo-1762926627917-278e7151ba9b?auto=format&fit=crop&w=900&q=75";

export default function Demo() {
  return (
    <div className="grid w-full max-w-6xl gap-x-5 gap-y-12 p-6 min-[700px]:grid-cols-3 lg:gap-x-8 lg:p-8">
      <NotchedProjectCard
        href="https://unsplash.com/photos/x7uQfg7W-cw"
        target="_blank"
        rel="noreferrer"
        title="Notifikasi bukan kelulusan"
        description="NPRA menyemak dokumen selepas produk dipasarkan. Siapa yang simpan PIF anda?"
        image={LAB}
        imageAlt="A person in a white coat working in a cosmetics lab"
        badge="Kosmetik"
        tags={["NPRA", "PIF"]}
        monochrome
        accent="#DA8956"
      />
      <NotchedProjectCard
        href="https://unsplash.com/photos/Pm0K9Y3EPUc"
        target="_blank"
        rel="noreferrer"
        title="Kolagen tak terus ke kulit"
        description="Paksi usus-kulit: metabolit, bukan bahan asal, yang sampai. Dakwaan kena ikut mekanisme."
        image={SKIN}
        imageAlt="Skincare products with smooth river stones and evergreen sprigs"
        badge="Sains kosmetik"
        tags={["Dakwaan", "Nutricosmetic"]}
        monochrome
        accent="#DA8956"
      />
      <NotchedProjectCard
        href="https://unsplash.com/photos/CBxpsG359I0"
        target="_blank"
        rel="noreferrer"
        title="Kedai runcit bukan pemegang SPHM"
        description="Sijil halal ikut skim: produk, premis makanan, rumah sembelihan. Peruncitan bukan salah satunya."
        image={SHELF}
        imageAlt="Shelves of packaged food items and jars"
        badge="Halal"
        tags={["JAKIM", "MPPHM 2020"]}
        monochrome
        accent="#DA8956"
      />
    </div>
  );
}
