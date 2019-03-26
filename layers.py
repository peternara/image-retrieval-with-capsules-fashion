from keras import layers, initializers
from keras import backend as K
from utils import squash
import tensorflow as tf


class Length(layers.Layer):
    def call(self, inputs, **kwargs):
        return K.sqrt(K.sum(K.square(inputs), -1))

    def compute_output_shape(self, input_shape):
        return input_shape[:-1]

    def get_config(self):
        return super(Length, self).get_config()


class Mask(layers.Layer):
    def call(self, inputs, **kwargs):
        if type(inputs) is list:
            assert len(inputs) == 2
            inputs, mask = inputs
        else:
            mask = K.one_hot(indices=K.argmax(K.sqrt(K.sum(K.square(inputs), -1)), 1),
                             num_classes=K.sqrt(K.sum(K.square(inputs), -1)).get_shape().as_list()[1])

        return K.batch_flatten(inputs * K.expand_dims(mask, -1))

    def compute_output_shape(self, input_shape):
        if type(input_shape[0]) is tuple:
            return tuple([None, input_shape[0][1] * input_shape[0][2]])
        else:
            return tuple([None, input_shape[1] * input_shape[2]])

    def get_config(self):
        return super(Mask, self).get_config()


def Conv_Block(x, filters, kernel_size, strides=1, padding='valid', name='conv_block'):
    # Stacked-convolutional layer
    out = layers.Conv2D(int(filters), kernel_size, strides, padding, name)(x)
    out = layers.BatchNormalization()(out)
    out = layers.LeakyReLU()(out)
    return out


def PrimaryCaps(inputs, dim_capsule, n_channels=32, kernel_size=9, strides=2, padding="same"):
    inputs = layers.Conv2D(filters=dim_capsule*n_channels, kernel_size=kernel_size, strides=strides, padding=padding,
                           name='primarycap_conv2d')(inputs)
    inputs = layers.Reshape(target_shape=[-1, dim_capsule], name='primarycap_reshape')(inputs)
    return layers.Lambda(squash, name='primarycap_squash')(inputs)


class FashionCaps(layers.Layer):
    def __init__(self, num_capsule, dim_capsule, routings=3, kernel_initializer='glorot_uniform', **kwargs):
        self.num_capsule = num_capsule
        self.dim_capsule = dim_capsule
        self.routings = routings
        self.kernel_initializer = initializers.get(kernel_initializer)
        super(FashionCaps, self).__init__(**kwargs)

    def build(self, input_shape):
        assert len(input_shape) >= 3
        self.input_num_capsule = input_shape[1]
        self.input_dim_capsule = input_shape[2]

        # Transform matrix
        self.W = self.add_weight(shape=[self.num_capsule, self.input_num_capsule,
                                        self.dim_capsule, self.input_dim_capsule],
                                 initializer=self.kernel_initializer,
                                 name='W')
        self.built = True

    def call(self, inputs, training=None):
        inputs = K.expand_dims(inputs, 1)
        inputs = K.tile(inputs, [1, self.num_capsule, 1, 1])
        inputs = K.map_fn(lambda x: K.batch_dot(x, self.W, [2, 3]), elems=inputs)

        # Dynamic routing
        b = tf.zeros(shape=[K.shape(inputs)[0], self.num_capsule, self.input_num_capsule])

        assert self.routings > 0
        for i in range(self.routings):
            outputs = squash(K.batch_dot(tf.nn.softmax(b, dim=1), inputs, [2, 2]))

            if i < self.routings - 1:
                b += K.batch_dot(outputs, inputs, [2, 3])

        return outputs

    def compute_output_shape(self, input_shape):
        return tuple([None, self.num_capsule, self.dim_capsule])

    def get_config(self):
        config = {
            'num_capsule': self.num_capsule,
            'dim_capsule': self.dim_capsule,
            'routings': self.routings
        }
        base_config = super(FashionCaps, self).get_config()
        new_config = list(base_config.items()) + list(config.items())
        return dict(new_config)